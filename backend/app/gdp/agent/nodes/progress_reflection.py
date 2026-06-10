"""GDP Agent 进度反思节点。"""

from __future__ import annotations

from typing import Any

from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.state import GDPState
from app.gdp.agent.tools.scene_tools import reflect_scene_result
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService


def build_progress_reflection_node(
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None = None,
):
    """构造进度反思节点。"""

    async def progress_reflection(state: GDPState) -> GDPState:
        task_run_id = state["task_run_id"]
        task_run = await task_service.get_task_run(task_run_id)
        decision_context = state.get("decision_context") or {}

        if task_run.status.value in {"WAITING_USER", "FAILED", "COMPLETED", "CANCELLED"}:
            return await _with_context_summary(
                task_service,
                subtask_service,
                task_run_id,
                {"current_phase": task_run.phase.value},
            )

        scene_result = decision_context.get("lastSceneResult")
        if scene_result:
            reflection = await reflect_scene_result(goal=task_run.userIntent, scene_result=scene_result)
            if reflection["completed"]:
                await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.SUCCESS)
                await task_service.mark_completed(
                    task_run_id,
                    final_summary=_build_success_summary(decision_context, scene_result),
                )
                result = {
                    "current_phase": DatagenTaskPhase.COMPLETED.value,
                    "task_context": {
                        "task_run_id": task_run_id,
                        "status": DatagenTaskStatus.COMPLETED.value,
                        "phase": DatagenTaskPhase.COMPLETED.value,
                    },
                    "decision_context": {"lastReflection": reflection},
                }
                return await _with_context_summary(task_service, subtask_service, task_run_id, result)
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
                result = {
                    "current_phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                    "task_context": {
                        "task_run_id": task_run_id,
                        "status": DatagenTaskStatus.RUNNING.value,
                        "phase": DatagenTaskPhase.SCENE_FULFILLMENT.value,
                    },
                    "decision_context": {"lastReflection": reflection},
                }
                return await _with_context_summary(task_service, subtask_service, task_run_id, result)
            await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.FAILED)
            result = {
                "current_phase": DatagenTaskPhase.FAILED.value,
                "decision_context": {"lastReflection": reflection},
            }
            return await _with_context_summary(task_service, subtask_service, task_run_id, result)

        await task_service.record_event(
            task_run_id,
            event_type="TASK_REFLECTED",
            phase=task_run.phase,
            message="当前阶段未完成造数任务，等待后续分支继续推进。",
            payload={
                "currentPhase": task_run.phase.value,
                "lastResultRef": state.get("last_result_ref"),
                "decisionKeys": sorted(decision_context.keys()),
            },
        )
        return await _with_context_summary(
            task_service,
            subtask_service,
            task_run_id,
            {"current_phase": task_run.phase.value},
        )

    return progress_reflection


async def _with_context_summary(
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None,
    task_run_id: str,
    result: dict[str, Any],
) -> GDPState:
    """在节点出口刷新轻量上下文摘要，避免 checkpoint 保留旧进度。"""

    return {
        **result,
        "context_summary": await load_gdp_context_summary(task_service, subtask_service, task_run_id),
    }


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


def _build_success_summary(decision_context: dict, scene_result: dict) -> str:
    selected = decision_context.get("selectedSceneCandidate") or {}
    contract = selected.get("contract") or {}
    scene_code = contract.get("sceneCode") or scene_result.get("sceneCode") or "未知场景"
    scene_run_id = scene_result.get("sceneRunId") or "未知运行记录"
    return f"造数任务已完成。执行场景 {scene_code}，场景运行记录 {scene_run_id}。"
