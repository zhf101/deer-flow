"""GDP Agent 进度反思节点。"""

from __future__ import annotations

from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.scene_tools import reflect_scene_result
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService


def build_progress_reflection_node(task_service: DatagenTaskService):
    """构造进度反思节点。"""

    async def progress_reflection(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        last_result = state.get("last_tool_result") or {}

        if task_run.status.value in {"WAITING_USER", "FAILED", "COMPLETED", "CANCELLED"}:
            return {"current_phase": task_run.phase.value}

        scene_result = last_result.get("sceneResult")
        if scene_result:
            reflection = await reflect_scene_result(goal=task_run.userIntent, scene_result=scene_result)
            if reflection["completed"]:
                await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.SUCCESS)
                await task_service.mark_completed(
                    task_run_id,
                    final_summary=_build_success_summary(last_result, scene_result),
                )
                return {"current_phase": DatagenTaskPhase.COMPLETED.value, "last_tool_result": {**last_result, "reflection": reflection}}
            if reflection.get("nextAction") == "SEARCH_NEXT_SCENE":
                await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.SUCCESS)
                await task_service.move_to_phase(
                    task_run_id,
                    status=DatagenTaskStatus.RUNNING,
                    phase=DatagenTaskPhase.SCENE_FULFILLMENT,
                    event_type="TASK_REFLECTED",
                    message="当前步骤尚未满足总体目标，回到已有场景满足阶段继续搜索下一步场景。",
                    payload=reflection,
                )
                return {
                    "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                    "last_tool_result": {**last_result, "reflection": reflection},
                }
            await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.FAILED)
            return {"current_phase": DatagenTaskPhase.FAILED.value, "last_tool_result": {**last_result, "reflection": reflection}}

        await task_service.record_event(
            task_run_id,
            event_type="TASK_REFLECTED",
            phase=task_run.phase,
            message="当前阶段未完成造数任务，等待后续分支继续推进。",
            payload={"currentPhase": task_run.phase.value, "lastToolResult": last_result},
        )
        return {"current_phase": task_run.phase.value, "last_tool_result": last_result}

    return progress_reflection


async def _record_reflection_step(
    task_service: DatagenTaskService,
    task_run_id: str,
    reflection: dict,
    scene_result: dict,
    status: DatagenTaskStepStatus,
) -> None:
    await task_service.record_task_step(
        task_run_id,
        phase=DatagenTaskPhase.PROGRESS_REFLECTION,
        step_type=DatagenTaskStepType.REFLECT,
        goal="校验当前场景执行结果是否满足总体造数目标。",
        status=status,
        selected_resource={
            "sceneCode": scene_result.get("sceneCode"),
            "sceneRunId": scene_result.get("sceneRunId"),
        },
        output=reflection,
        scene_run_id=scene_result.get("sceneRunId"),
    )


def _build_success_summary(last_result: dict, scene_result: dict) -> str:
    selected = last_result.get("selectedCandidate") or {}
    contract = selected.get("contract") or {}
    scene_code = contract.get("sceneCode") or scene_result.get("sceneCode") or "未知场景"
    scene_run_id = scene_result.get("sceneRunId") or "未知运行记录"
    return f"造数任务已完成。执行场景 {scene_code}，场景运行记录 {scene_run_id}。"
