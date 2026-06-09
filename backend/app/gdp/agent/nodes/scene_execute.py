"""GDP Agent 场景执行节点。"""

from __future__ import annotations

from typing import Any

from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.scene_tools import bind_scene_inputs, run_datagen_scene_for_task
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_scene_execute_node(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
):
    """构造用户确认后的场景执行节点。"""

    async def scene_execute(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        last_result = state.get("last_tool_result") or {}
        selected = last_result.get("selectedCandidate") or {}
        contract = selected.get("contract") or {}
        scene_code = contract.get("sceneCode")
        if not scene_code:
            await task_service.fail_task(
                task_run_id,
                failure_type="SCENE_SELECTION_MISSING",
                failure_message="用户确认后没有找到待执行的候选场景，任务终止。",
            )
            return {"current_phase": DatagenTaskPhase.FAILED.value, "last_tool_result": last_result}

        confirmation = state.get("confirmation_result")
        if not _is_approved(confirmation):
            await task_service.fail_task(
                task_run_id,
                failure_type="USER_REJECTED_WRITE_SCENE",
                failure_message="用户未确认执行写操作场景，造数任务已终止。",
            )
            return {"current_phase": DatagenTaskPhase.FAILED.value, "last_tool_result": last_result}

        visible_variables = [_visible_variable_summary(item) for item in task_run.visibleVariables]
        bindings = await bind_scene_inputs(
            catalog_service,
            scene_code=scene_code,
            user_inputs=state.get("user_inputs") or {},
            visible_variables=visible_variables,
        )
        scene_result = await run_datagen_scene_for_task(
            task_service,
            scene_service,
            task_run_id=task_run_id,
            scene_code=scene_code,
            env_code=task_run.envCode,
            input_params=bindings["bindings"],
            goal=task_run.userIntent,
        )
        return {
            "current_phase": DatagenTaskPhase.PROGRESS_REFLECTION.value,
            "last_tool_result": {**last_result, "inputBinding": bindings, "sceneResult": scene_result},
        }

    return scene_execute


def _is_approved(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        for key in ("approved", "confirm", "confirmed", "yes"):
            if value.get(key) is True:
                return True
        text = str(value.get("reply") or value.get("answer") or "")
        return _is_positive_text(text)
    if isinstance(value, str):
        return _is_positive_text(value)
    return False


def _is_positive_text(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"y", "yes", "ok", "true", "确认", "同意", "继续", "执行"}


def _visible_variable_summary(variable: Any) -> dict[str, Any]:
    return {
        "name": variable.name,
        "semanticType": variable.semanticType,
        "label": variable.label,
        "valueSchema": variable.valueSchema,
        "valuePreview": None if variable.sensitive else variable.valuePreview,
        "valueSize": variable.valueSize.model_dump(mode="json") if variable.valueSize else None,
        "sensitive": variable.sensitive,
        "confidence": variable.confidence,
    }
