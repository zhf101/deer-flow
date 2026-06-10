"""GDP Agent 进度反思节点。"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from app.gdp.agent.llm.decision import reflect_gdp_scene_result
from app.gdp.agent.llm.events import llm_decision_payload, llm_failure_payload
from app.gdp.agent.llm.schemas import GDPReflectionDecision
from app.gdp.agent.middlewares.context_compression import load_gdp_context_summary
from app.gdp.agent.state import NODE_ATTEMPT_CAP, GDPState, node_attempt_cap_exceeded
from app.gdp.agent.tools.scene_tools import reflect_scene_result
from app.gdp.datagen.config.task.models import (
    DatagenTaskPhase,
    DatagenTaskStatus,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)
from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService
from deerflow.config.app_config import AppConfig


def build_progress_reflection_node(
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None = None,
    *,
    app_config: AppConfig | None = None,
    llm_enabled: bool = False,
    llm_model: Any | None = None,
):
    """构造进度反思节点。"""

    async def progress_reflection(state: GDPState, config: RunnableConfig | None = None) -> GDPState:
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

        capped_node = node_attempt_cap_exceeded(state)
        if capped_node is not None:
            return await _fail_on_progress_loop(
                task_service,
                subtask_service,
                task_run_id,
                node_name=capped_node,
                attempts=state.get("node_attempts") or {},
            )

        scene_result = decision_context.get("lastSceneResult")
        if scene_result:
            reflection, llm_state_update = await _reflect_with_llm_or_rules(
                task_service,
                task_run_id,
                goal=task_run.userIntent,
                scene_result=scene_result,
                context_summary=state.get("context_summary") or {},
                config=config,
                app_config=app_config,
                llm_enabled=llm_enabled,
                llm_model=llm_model,
            )
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
                    **llm_state_update,
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
                    **llm_state_update,
                }
                return await _with_context_summary(task_service, subtask_service, task_run_id, result)
            await _record_reflection_step(task_service, task_run_id, reflection, scene_result, DatagenTaskStepStatus.FAILED)
            result = {
                "current_phase": DatagenTaskPhase.FAILED.value,
                "decision_context": {"lastReflection": reflection},
                **llm_state_update,
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


async def _fail_on_progress_loop(
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None,
    task_run_id: str,
    *,
    node_name: str,
    attempts: dict[str, Any],
) -> GDPState:
    """进度环硬上限收口：节点重复进入超限即判定阶段振荡，任务直接失败。"""

    failure_message = f"业务节点 {node_name} 累计进入 {attempts.get(node_name)} 次，超过硬上限 {NODE_ATTEMPT_CAP}，判定为阶段振荡，任务终止。"
    await task_service.fail_task(
        task_run_id,
        failure_type="PROGRESS_LOOP_DETECTED",
        failure_message=failure_message,
    )
    return await _with_context_summary(
        task_service,
        subtask_service,
        task_run_id,
        {
            "current_phase": DatagenTaskPhase.FAILED.value,
            "task_context": {
                "task_run_id": task_run_id,
                "status": DatagenTaskStatus.FAILED.value,
                "phase": DatagenTaskPhase.FAILED.value,
            },
        },
    )


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


async def _reflect_with_llm_or_rules(
    task_service: DatagenTaskService,
    task_run_id: str,
    *,
    goal: str,
    scene_result: dict[str, Any],
    context_summary: dict[str, Any],
    config: RunnableConfig | None,
    app_config: AppConfig | None,
    llm_enabled: bool,
    llm_model: Any | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """优先使用模型反思场景结果，失败时回退到规则反思。"""

    if llm_enabled:
        try:
            decision = await reflect_gdp_scene_result(
                goal=goal,
                scene_result=scene_result,
                context_summary=context_summary,
                config=config,
                app_config=app_config,
                model=llm_model,
            )
            event = await task_service.record_event(
                task_run_id,
                event_type="LLM_RESULT_REFLECTED",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                message="模型已判断场景执行结果是否满足总体造数目标。",
                payload=llm_decision_payload(decision),
            )
            return decision.model_dump(mode="json"), _reflection_llm_state_update(decision, event.eventId, event.eventType)
        except Exception as exc:
            event = await task_service.record_event(
                task_run_id,
                event_type="LLM_RESULT_REFLECTION_FAILED",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                message="模型反思场景执行结果失败，已回退到规则判断。",
                payload=llm_failure_payload(exc),
            )
            fallback = await reflect_scene_result(goal=goal, scene_result=scene_result)
            return fallback, {
                "last_llm_decision": {
                    "decisionType": "result_reflection",
                    "decisionSource": "fallback_rule",
                    "errorType": type(exc).__name__,
                },
                "llm_decision_refs": [
                    {
                        "eventId": event.eventId,
                        "eventType": event.eventType,
                        "decisionType": "result_reflection",
                    }
                ],
            }
    return await reflect_scene_result(goal=goal, scene_result=scene_result), {}


def _reflection_llm_state_update(
    decision: GDPReflectionDecision,
    event_id: str,
    event_type: str,
) -> dict[str, Any]:
    """生成反思模型决策的 checkpoint 轻量摘要。"""

    return {
        "last_llm_decision": {
            "decisionType": "result_reflection",
            "completed": decision.completed,
            "nextAction": decision.nextAction,
            "confidence": decision.confidence,
            "reason": decision.reason,
        },
        "llm_decision_refs": [
            {
                "eventId": event_id,
                "eventType": event_type,
                "decisionType": "result_reflection",
            }
        ],
    }


def _build_success_summary(decision_context: dict, scene_result: dict) -> str:
    selected = decision_context.get("selectedSceneCandidate") or {}
    contract = selected.get("contract") or {}
    scene_code = contract.get("sceneCode") or scene_result.get("sceneCode") or "未知场景"
    scene_run_id = scene_result.get("sceneRunId") or "未知运行记录"
    return f"造数任务已完成。执行场景 {scene_code}，场景运行记录 {scene_run_id}。"
