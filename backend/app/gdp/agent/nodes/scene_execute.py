"""GDP Agent 场景执行节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.middlewares.business_guardrail import GDPToolApprovalContext
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.registry import assert_gdp_registered_tool_allowed
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

    async def scene_execute(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        decision_context = state.get("decision_context") or {}
        selected = decision_context.get("selectedSceneCandidate") or {}
        contract = selected.get("contract") or {}
        scene_code = contract.get("sceneCode") or decision_context.get("selectedSceneCode")
        if not scene_code:
            await task_service.fail_task(
                task_run_id,
                failure_type="SCENE_SELECTION_MISSING",
                failure_message="用户确认后没有找到待执行的候选场景，任务终止。",
            )
            return {"current_phase": DatagenTaskPhase.FAILED.value}

        confirmation = state.get("confirmation_result")
        if not _is_approved(confirmation):
            await task_service.fail_task(
                task_run_id,
                failure_type="USER_REJECTED_WRITE_SCENE",
                failure_message="用户未确认执行写操作场景，造数任务已终止。",
            )
            return {"current_phase": DatagenTaskPhase.FAILED.value}

        visible_variables = [_visible_variable_summary(item) for item in task_run.visibleVariables]
        bindings = await bind_scene_inputs(
            catalog_service,
            scene_code=scene_code,
            user_inputs=state.get("user_inputs") or {},
            visible_variables=visible_variables,
        )
        assert_gdp_registered_tool_allowed(
            "run_datagen_scene_for_task",
            {
                "task_run_id": task_run_id,
                "scene_code": scene_code,
                "env_code": task_run.envCode,
                "input_params": bindings["bindings"],
            },
            GDPToolApprovalContext(
                allowBusinessWrite=True,
                operator=_operator(state),
                reason="用户已确认执行写操作场景。",
            ),
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
        result_ref = _scene_result_ref(str(scene_code), scene_result)
        return {
            "current_phase": DatagenTaskPhase.PROGRESS_REFLECTION.value,
            "decision_context": {
                "selectedSceneCode": scene_code,
                "selectedSceneCandidate": selected,
                "inputBinding": bindings,
                "lastSceneResult": scene_result,
            },
            "last_result_ref": result_ref,
        }

    return scene_execute


def _operator(state: GDPState) -> str | None:
    runtime_context = state.get("runtime_context") or {}
    if isinstance(runtime_context, dict) and runtime_context.get("operator"):
        return str(runtime_context["operator"])
    return None


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


def _scene_result_ref(scene_code: str, scene_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_type": "SCENE_RUN",
        "task_step_id": scene_result.get("taskStepId"),
        "scene_run_id": scene_result.get("sceneRunId"),
        "scene_code": scene_code,
        "summary": {
            "success": scene_result.get("success"),
            "sceneStatus": scene_result.get("sceneStatus"),
            "outputKeys": scene_result.get("outputKeys") or sorted((scene_result.get("finalOutput") or {}).keys()),
            "finalOutputSize": scene_result.get("finalOutputSize"),
            "errorCount": len(scene_result.get("errors") or []),
        },
    }
