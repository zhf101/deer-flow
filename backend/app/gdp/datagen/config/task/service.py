"""造数任务控制面业务服务层。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import HTTPException

from app.gdp.datagen.config.task.models import (
    DatagenTaskContinueResponse,
    DatagenTaskEnvSource,
    DatagenTaskEventResponse,
    DatagenTaskPhase,
    DatagenTaskPlan,
    DatagenTaskPlanStep,
    DatagenTaskRunCreateRequest,
    DatagenTaskRunResponse,
    DatagenTaskStatus,
    DatagenTaskStepResponse,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
    DatagenTaskSummaryResponse,
    DatagenTaskUserReplyRequest,
    GoalStackItem,
    VisibleVariable,
    VisibleVariableValueSize,
)
from app.gdp.datagen.config.task.repository import (
    DatagenTaskConflictError,
    DatagenTaskNotFoundError,
    DatagenTaskRepository,
)
from app.gdp.datagen.config.task.validation import normalize_task_intent
from app.gdp.datagen.redaction import redact_sensitive_payload

T = TypeVar("T")

DEFAULT_ENV_CODE = "DEV"
VARIABLE_PREVIEW_ITEM_LIMIT = 2
VARIABLE_PREVIEW_FIELD_LIMIT = 8
VARIABLE_PREVIEW_STRING_LIMIT = 256
TERMINAL_TASK_STATUSES = frozenset(
    {
        DatagenTaskStatus.COMPLETED,
        DatagenTaskStatus.FAILED,
        DatagenTaskStatus.CANCELLED,
    }
)
RECOVERABLE_STEP_STATUSES = frozenset(
    {
        DatagenTaskStepStatus.PENDING,
        DatagenTaskStepStatus.RUNNING,
    }
)


class DatagenTaskService:
    """造数任务控制面服务。"""

    def __init__(self, repository: DatagenTaskRepository) -> None:
        self._repo = repository

    async def create_task_run(
        self,
        request: DatagenTaskRunCreateRequest,
        *,
        operator: str | None = None,
        deerflow_thread_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        request = normalize_task_intent(request)
        env_code = request.envCode or DEFAULT_ENV_CODE
        env_source = DatagenTaskEnvSource.USER_EXPLICIT if request.envCode else DatagenTaskEnvSource.SYSTEM_DEFAULT
        normalized_goal = {
            **(request.normalizedGoal or {}),
            "rawIntent": request.userIntent,
            "inputs": request.inputs,
            "envCode": env_code,
            "envSource": env_source.value,
        }
        goal_stack = [
            GoalStackItem(
                goalType="DATAGEN_TASK",
                goal=request.userIntent,
                phase=DatagenTaskPhase.SCENE_FULFILLMENT,
            )
        ]
        plan = _build_initial_plan(request.userIntent)
        visible_variables = [
            VisibleVariable(
                name=key,
                source="${task.inputs." + key + "}",
                label=key,
                value=value,
                valuePreview=value,
            )
            for key, value in request.inputs.items()
        ]
        task_run = await self._guard(
            lambda: self._repo.create_task_run(
                user_intent=request.userIntent,
                env_code=env_code,
                env_source=env_source,
                normalized_goal=normalized_goal,
                goal_stack=goal_stack,
                plan=plan,
                visible_variables=visible_variables,
                operator=operator,
                deerflow_thread_id=deerflow_thread_id,
            )
        )
        await self.record_event(
            task_run.taskRunId,
            event_type="TASK_CREATED",
            phase=DatagenTaskPhase.INTAKE,
            message="已创建造数任务。",
            payload={"envCode": env_code, "envSource": env_source.value},
        )
        if env_source == DatagenTaskEnvSource.SYSTEM_DEFAULT:
            await self.record_event(
                task_run.taskRunId,
                event_type="DEFAULT_ENV_SELECTED",
                phase=DatagenTaskPhase.INTAKE,
                message="用户未指定环境，后端默认使用 DEV。",
                payload={"envCode": env_code},
            )
        await self.record_event(
            task_run.taskRunId,
            event_type="TASK_PLAN_CREATED",
            phase=DatagenTaskPhase.INTAKE,
            message="已生成造数任务初始总体计划。",
            payload=plan.model_dump(mode="json"),
        )
        return task_run

    async def list_task_runs(
        self,
        *,
        status: DatagenTaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DatagenTaskRunResponse]:
        return await self._guard(lambda: self._repo.list_task_runs(status=status, limit=limit, offset=offset))

    async def get_task_run(self, task_run_id: str) -> DatagenTaskRunResponse:
        return await self._guard(lambda: self._repo.get_task_run(task_run_id))

    async def continue_task(self, task_run_id: str) -> DatagenTaskContinueResponse:
        task_run = await self._guard(lambda: self._repo.get_task_run(task_run_id))
        await self.record_event(
            task_run_id,
            event_type="TASK_CONTINUE_REQUESTED",
            phase=task_run.phase,
            message="收到继续推进任务请求。",
            payload={},
        )
        if task_run.status in TERMINAL_TASK_STATUSES:
            await self.record_event(
                task_run_id,
                event_type="TASK_CONTINUE_REJECTED",
                phase=task_run.phase,
                message="任务已结束，不能继续推进。",
                payload={"status": task_run.status.value},
            )
            raise HTTPException(status_code=409, detail="任务已结束，不能继续推进。")
        if task_run.status == DatagenTaskStatus.WAITING_USER:
            return DatagenTaskContinueResponse(taskRun=task_run, message="任务正在等待用户回复，请通过 user-reply 恢复中断点。")
        recovered_steps = await self.recover_non_terminal_steps(
            task_run_id,
            reason="继续推进任务前恢复上一次运行遗留的非终态步骤。",
        )
        if not task_run.deerflowThreadId:
            message = "任务尚未绑定 DeerFlow thread，仅记录继续请求。"
            if recovered_steps:
                message = f"{message} 已恢复 {len(recovered_steps)} 个非终态步骤。"
            return DatagenTaskContinueResponse(taskRun=task_run, message=message)
        message = "任务控制面已记录继续请求，可提交 GDP Agent 运行继续推进。"
        if recovered_steps:
            message = f"{message} 已恢复 {len(recovered_steps)} 个非终态步骤。"
        return DatagenTaskContinueResponse(taskRun=task_run, message=message)

    async def bind_deerflow_run(
        self,
        task_run_id: str,
        *,
        deerflow_thread_id: str | None = None,
        deerflow_run_id: str | None = None,
        last_checkpoint_id: str | None = None,
    ) -> DatagenTaskRunResponse:
        return await self._guard(
            lambda: self._repo.update_deerflow_binding(
                task_run_id,
                deerflow_thread_id=deerflow_thread_id,
                deerflow_run_id=deerflow_run_id,
                last_checkpoint_id=last_checkpoint_id,
            )
        )

    async def cancel_task(self, task_run_id: str) -> DatagenTaskRunResponse:
        task_run = await self._guard(
            lambda: self._repo.update_status(
                task_run_id,
                status=DatagenTaskStatus.CANCELLED,
                phase=DatagenTaskPhase.FAILED,
                final_summary="任务已取消。",
            )
        )
        await self.record_event(
            task_run_id,
            event_type="TASK_CANCELLED",
            phase=task_run.phase,
            message="任务已取消。",
            payload={},
        )
        return task_run

    async def move_to_phase(
        self,
        task_run_id: str,
        *,
        status: DatagenTaskStatus,
        phase: DatagenTaskPhase,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> DatagenTaskRunResponse:
        task_run = await self._guard(
            lambda: self._repo.update_status(
                task_run_id,
                status=status,
                phase=phase,
            )
        )
        await self.record_event(
            task_run_id,
            event_type=event_type,
            phase=phase,
            message=message,
            payload=payload or {},
        )
        return task_run

    async def mark_waiting_user(
        self,
        task_run_id: str,
        *,
        pending_interrupts: dict[str, Any],
        message: str,
    ) -> DatagenTaskRunResponse:
        pending_interrupts = redact_sensitive_payload(pending_interrupts)
        steps = await self.list_steps(task_run_id)
        task_run = await self._guard(
            lambda: self._repo.update_status(
                task_run_id,
                status=DatagenTaskStatus.WAITING_USER,
                phase=DatagenTaskPhase.WAITING_USER,
                pending_interrupts=pending_interrupts,
            )
        )
        await self.record_task_step(
            task_run_id,
            step_no=len(steps) + 1,
            phase=DatagenTaskPhase.WAITING_USER,
            step_type=DatagenTaskStepType.ASK_USER,
            goal=message,
            status=DatagenTaskStepStatus.WAITING_USER,
            selected_resource={"questionType": pending_interrupts.get("questionType")},
            output=pending_interrupts,
        )
        await self.record_event(
            task_run_id,
            event_type="ASK_USER",
            phase=DatagenTaskPhase.WAITING_USER,
            message=message,
            payload=pending_interrupts,
        )
        return task_run

    async def mark_completed(self, task_run_id: str, *, final_summary: str) -> DatagenTaskRunResponse:
        task_run = await self._guard(
            lambda: self._repo.update_status(
                task_run_id,
                status=DatagenTaskStatus.COMPLETED,
                phase=DatagenTaskPhase.COMPLETED,
                final_summary=final_summary,
            )
        )
        await self.record_event(
            task_run_id,
            event_type="TASK_COMPLETED",
            phase=DatagenTaskPhase.COMPLETED,
            message=final_summary,
            payload={},
        )
        return task_run

    async def record_user_reply(
        self,
        task_run_id: str,
        request: DatagenTaskUserReplyRequest,
    ) -> DatagenTaskEventResponse:
        task_run = await self.get_task_run(task_run_id)
        return await self.record_event(
            task_run_id,
            event_type="USER_REPLY",
            phase=task_run.phase,
            message="已记录用户回复。",
            payload={"reply": redact_sensitive_payload(request.reply)},
        )

    async def list_steps(self, task_run_id: str) -> list[DatagenTaskStepResponse]:
        return await self._guard(lambda: self._repo.list_steps(task_run_id))

    async def record_scene_step(
        self,
        task_run_id: str,
        *,
        step_no: int,
        goal: str,
        selected_resource: dict[str, Any],
        input_binding: dict[str, Any],
        output: dict[str, Any],
        scene_run_id: str | None,
        status: DatagenTaskStepStatus,
    ) -> DatagenTaskStepResponse:
        return await self._guard(
            lambda: self._repo.create_step(
                task_run_id=task_run_id,
                step_no=step_no,
                phase=DatagenTaskPhase.SCENE_EXECUTING,
                step_type=DatagenTaskStepType.RUN_SCENE,
                goal=goal,
                status=status,
                selected_resource=selected_resource,
                input_binding=input_binding,
                output=output,
                scene_run_id=scene_run_id,
            )
        )

    async def record_task_step(
        self,
        task_run_id: str,
        *,
        step_no: int | None = None,
        phase: DatagenTaskPhase,
        step_type: DatagenTaskStepType,
        goal: str,
        status: DatagenTaskStepStatus,
        selected_resource: dict[str, Any] | None = None,
        input_binding: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        scene_run_id: str | None = None,
    ) -> DatagenTaskStepResponse:
        if step_no is None:
            step_no = len(await self.list_steps(task_run_id)) + 1
        return await self._guard(
            lambda: self._repo.create_step(
                task_run_id=task_run_id,
                step_no=step_no,
                phase=phase,
                step_type=step_type,
                goal=goal,
                status=status,
                selected_resource=selected_resource,
                input_binding=input_binding,
                output=output,
                scene_run_id=scene_run_id,
            )
        )

    async def recover_non_terminal_steps(
        self,
        task_run_id: str,
        *,
        reason: str,
    ) -> list[DatagenTaskStepResponse]:
        """把上一次运行遗留的 PENDING/RUNNING 步骤标记为可恢复失败。"""

        steps = await self.list_steps(task_run_id)
        recovered: list[DatagenTaskStepResponse] = []
        for step in steps:
            if step.status not in RECOVERABLE_STEP_STATUSES:
                continue
            recovered.append(
                await self._guard(
                    lambda step=step: self._repo.update_step_status(
                        task_run_id,
                        step.taskStepId,
                        status=DatagenTaskStepStatus.FAILED,
                        error_type="RECOVERED_NON_TERMINAL_STEP",
                        error_message=reason,
                    )
                )
            )
        if recovered:
            task_run = await self.get_task_run(task_run_id)
            await self.record_event(
                task_run_id,
                event_type="TASK_STEPS_RECOVERED",
                phase=task_run.phase,
                message="已恢复上一次运行遗留的非终态步骤。",
                payload={
                    "reason": reason,
                    "steps": [
                        {
                            "taskStepId": step.taskStepId,
                            "stepNo": step.stepNo,
                            "phase": step.phase.value,
                            "stepType": step.stepType.value,
                            "status": step.status.value,
                        }
                        for step in recovered
                    ],
                },
            )
        return recovered

    async def append_visible_variables_from_scene_result(
        self,
        task_run_id: str,
        *,
        scene_code: str,
        scene_run_id: str,
        final_output: dict[str, Any],
    ) -> list[VisibleVariable]:
        """把场景最终输出摘要化后写入任务变量栈。"""

        task_run = await self.get_task_run(task_run_id)
        variables_by_name = {item.name: item for item in task_run.visibleVariables}
        created_names: list[str] = []
        for name, value in final_output.items():
            variable = _build_visible_variable_from_value(
                name=name,
                value=value,
                source=f"${{task.sceneRuns.{scene_run_id}.finalOutput.{name}}}",
            )
            variables_by_name[name] = variable
            created_names.append(name)

        variables = list(variables_by_name.values())
        await self._guard(
            lambda: self._repo.update_visible_variables(
                task_run_id,
                visible_variables=variables,
            )
        )
        if created_names:
            await self.record_event(
                task_run_id,
                event_type="VARIABLE_STACK_UPDATED",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                message="已把场景输出写入任务变量栈。",
                payload={
                    "sceneCode": scene_code,
                    "sceneRunId": scene_run_id,
                    "variables": created_names,
                },
            )
        return variables

    async def append_visible_variables_from_mcp_result(
        self,
        task_run_id: str,
        *,
        capability_name: str,
        output: dict[str, Any],
        sensitive: bool = False,
        storage_ref: str | None = None,
    ) -> list[VisibleVariable]:
        """把 MCP capability 输出摘要化后写入任务变量栈。"""

        task_run = await self.get_task_run(task_run_id)
        variables_by_name = {item.name: item for item in task_run.visibleVariables}
        created_names: list[str] = []
        for name, value in output.items():
            variable = _build_visible_variable_from_value(
                name=name,
                value=value,
                source=f"${{task.mcp.{capability_name}.output.{name}}}",
            )
            if sensitive:
                variable = variable.model_copy(update={"sensitive": True, "valuePreview": None, "storageRef": storage_ref})
            elif storage_ref:
                variable = variable.model_copy(update={"storageRef": storage_ref})
            variables_by_name[name] = variable
            created_names.append(name)

        variables = list(variables_by_name.values())
        await self._guard(
            lambda: self._repo.update_visible_variables(
                task_run_id,
                visible_variables=variables,
            )
        )
        if created_names:
            await self.record_event(
                task_run_id,
                event_type="VARIABLE_STACK_UPDATED",
                phase=DatagenTaskPhase.PROGRESS_REFLECTION,
                message="已把 MCP capability 输出写入任务变量栈。",
                payload={
                    "capabilityName": capability_name,
                    "variables": created_names,
                    "storageRef": storage_ref,
                    "sensitive": sensitive,
                },
            )
        return variables

    async def fail_task(
        self,
        task_run_id: str,
        *,
        failure_type: str,
        failure_message: str,
    ) -> DatagenTaskRunResponse:
        task_run = await self._guard(
            lambda: self._repo.update_status(
                task_run_id,
                status=DatagenTaskStatus.FAILED,
                phase=DatagenTaskPhase.FAILED,
                failure_type=failure_type,
                failure_message=failure_message,
            )
        )
        await self.record_event(
            task_run_id,
            event_type="TASK_FAILED",
            phase=DatagenTaskPhase.FAILED,
            message=failure_message,
            payload={"failureType": failure_type},
        )
        return task_run

    async def list_events(self, task_run_id: str) -> list[DatagenTaskEventResponse]:
        return await self._guard(lambda: self._repo.list_events(task_run_id))

    async def get_summary(self, task_run_id: str) -> DatagenTaskSummaryResponse:
        task_run = await self.get_task_run(task_run_id)
        return DatagenTaskSummaryResponse(
            taskRunId=task_run.taskRunId,
            status=task_run.status,
            phase=task_run.phase,
            finalSummary=task_run.finalSummary,
            failureType=task_run.failureType,
            failureMessage=task_run.failureMessage,
        )

    async def record_event(
        self,
        task_run_id: str,
        *,
        event_type: str,
        phase: DatagenTaskPhase,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> DatagenTaskEventResponse:
        payload = redact_sensitive_payload(payload or {})
        return await self._guard(
            lambda: self._repo.record_event(
                task_run_id=task_run_id,
                event_type=event_type,
                phase=phase,
                message=message,
                payload=payload,
            )
        )

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except DatagenTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DatagenTaskConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _build_visible_variable_from_value(*, name: str, value: Any, source: str) -> VisibleVariable:
    value_schema = _summarize_schema(value)
    value_preview = _preview_value(value)
    return VisibleVariable(
        name=name,
        source=source,
        label=name,
        value=value,
        valueSchema=value_schema,
        valuePreview=value_preview,
        valueSize=VisibleVariableValueSize(
            charCount=len(_json_text(value)),
            itemCount=_item_count(value),
        ),
    )


def _summarize_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {key: _summarize_schema(item) for key, item in list(value.items())[:VARIABLE_PREVIEW_FIELD_LIMIT]},
        }
    if isinstance(value, list):
        first = value[0] if value else None
        return {
            "type": "array",
            "itemSchema": _summarize_schema(first) if first is not None else None,
        }
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    return {"type": "string"}


def _preview_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _preview_value(item)
            for key, item in list(value.items())[:VARIABLE_PREVIEW_FIELD_LIMIT]
        }
    if isinstance(value, list):
        return [_preview_value(item) for item in value[:VARIABLE_PREVIEW_ITEM_LIMIT]]
    if isinstance(value, str):
        return value[:VARIABLE_PREVIEW_STRING_LIMIT]
    return value


def _item_count(value: Any) -> int | None:
    if isinstance(value, (list, dict)):
        return len(value)
    return None


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _build_initial_plan(user_intent: str) -> DatagenTaskPlan:
    return DatagenTaskPlan(
        summary=f"围绕「{user_intent}」优先复用已发布造数场景；不足时逐层下探到场景设计、Source 配置和基础配置。",
        steps=[
            DatagenTaskPlanStep(
                stepNo=1,
                stepType=DatagenTaskStepType.RUN_SCENE,
                goal="搜索可复用的已发布造数场景，绑定入参后执行。",
            ),
            DatagenTaskPlanStep(
                stepNo=2,
                stepType=DatagenTaskStepType.REFLECT,
                goal="校验场景执行结果是否满足总体目标，必要时继续搜索下一步场景。",
            ),
            DatagenTaskPlanStep(
                stepNo=3,
                stepType=DatagenTaskStepType.DESIGN_SCENE,
                goal="没有可用场景时，基于已有 HTTP/SQL Source 生成并发布新场景。",
            ),
            DatagenTaskPlanStep(
                stepNo=4,
                stepType=DatagenTaskStepType.CONFIG_HTTP_SOURCE,
                goal="缺少 HTTP 原子能力时，引导补充 HTTP Source 配置。",
            ),
            DatagenTaskPlanStep(
                stepNo=5,
                stepType=DatagenTaskStepType.CONFIG_SQL_SOURCE,
                goal="缺少 SQL 原子能力时，引导补充 SQL Source 配置。",
            ),
            DatagenTaskPlanStep(
                stepNo=6,
                stepType=DatagenTaskStepType.CONFIG_INFRA,
                goal="Source 依赖的系统、环境、服务端点或数据源缺失时，引导补齐基础配置。",
            ),
        ],
    )
