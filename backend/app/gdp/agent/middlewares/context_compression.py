"""GDP Agent 上下文压缩摘要工具。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.gdp.datagen.config.task.service import DatagenTaskService
from app.gdp.datagen.config.task.subtask_service import DatagenTaskSubtaskService


async def load_gdp_context_summary(
    task_service: DatagenTaskService,
    subtask_service: DatagenTaskSubtaskService | None,
    task_run_id: str,
) -> dict[str, Any]:
    """从业务权威表加载轻量上下文摘要。"""

    task_run = await task_service.get_task_run(task_run_id)
    steps = await task_service.list_steps(task_run_id)
    subtasks = await subtask_service.list_subtasks(task_run_id) if subtask_service is not None else []
    return build_gdp_context_summary(task_run=task_run, steps=steps, subtasks=subtasks)


def build_gdp_context_summary(
    *,
    task_run: Any,
    steps: list[Any],
    subtasks: list[Any] | None = None,
) -> dict[str, Any]:
    """生成适合进入 checkpoint 和 Prompt 的 GDP 任务摘要。"""

    subtasks = subtasks or []
    plan_steps = list(getattr(getattr(task_run, "plan", None), "steps", []) or [])
    completed_steps = [step for step in steps if _enum_value(getattr(step, "status", None)) == "SUCCESS"]
    active_steps = [
        step
        for step in steps
        if _enum_value(getattr(step, "status", None)) in {"PENDING", "RUNNING", "WAITING_USER"}
    ]
    active_subtasks = [
        subtask
        for subtask in subtasks
        if _enum_value(getattr(subtask, "status", None)) in {"PENDING", "RUNNING", "WAITING_USER"}
    ]
    return {
        "goalAnchor": _goal_anchor(task_run),
        "plan": _plan_summary(getattr(task_run, "plan", None), plan_steps),
        "variableStack": _variable_stack_summary(getattr(task_run, "visibleVariables", []) or []),
        "steps": {
            "total": len(steps),
            "statusCounts": _status_counts(steps),
            "completed": [_step_summary(step) for step in completed_steps[-8:]],
            "active": [_step_summary(step) for step in active_steps[-8:]],
            "recent": [_step_summary(step) for step in steps[-8:]],
        },
        "subtasks": {
            "total": len(subtasks),
            "statusCounts": _status_counts(subtasks),
            "active": [_subtask_summary(subtask) for subtask in active_subtasks[-8:]],
            "recent": [_subtask_summary(subtask) for subtask in subtasks[-8:]],
        },
        "unfinishedGoals": _unfinished_goals(task_run, plan_steps, active_steps, active_subtasks),
    }


def _goal_anchor(task_run: Any) -> dict[str, Any]:
    return {
        "taskRunId": getattr(task_run, "taskRunId", None),
        "userIntent": getattr(task_run, "userIntent", None),
        "envCode": getattr(task_run, "envCode", None),
        "status": _enum_value(getattr(task_run, "status", None)),
        "phase": _enum_value(getattr(task_run, "phase", None)),
        "goalStack": [_model_dump(item) for item in getattr(task_run, "goalStack", []) or []],
    }


def _plan_summary(plan: Any, plan_steps: list[Any]) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "summary": getattr(plan, "summary", None),
        "steps": [
            {
                "stepNo": getattr(step, "stepNo", None),
                "stepType": _enum_value(getattr(step, "stepType", None)),
                "goal": getattr(step, "goal", None),
                "status": _enum_value(getattr(step, "status", None)),
            }
            for step in plan_steps
        ],
    }


def _variable_stack_summary(variables: list[Any]) -> dict[str, Any]:
    return {
        "count": len(variables),
        "items": [
            {
                "name": getattr(variable, "name", None),
                "source": getattr(variable, "source", None),
                "semanticType": getattr(variable, "semanticType", None),
                "label": getattr(variable, "label", None),
                "valueSchema": getattr(variable, "valueSchema", None),
                "valuePreview": None if getattr(variable, "sensitive", False) else getattr(variable, "valuePreview", None),
                "valueSize": _model_dump(getattr(variable, "valueSize", None)),
                "sensitive": bool(getattr(variable, "sensitive", False)),
                "confidence": getattr(variable, "confidence", None),
            }
            for variable in variables
        ],
    }


def _step_summary(step: Any) -> dict[str, Any]:
    output = getattr(step, "output", None)
    return {
        "taskStepId": getattr(step, "taskStepId", None),
        "stepNo": getattr(step, "stepNo", None),
        "phase": _enum_value(getattr(step, "phase", None)),
        "stepType": _enum_value(getattr(step, "stepType", None)),
        "goal": getattr(step, "goal", None),
        "status": _enum_value(getattr(step, "status", None)),
        "sceneRunId": getattr(step, "sceneRunId", None),
        "selectedResource": _resource_summary(getattr(step, "selectedResource", None)),
        "inputKeys": sorted((getattr(step, "inputBinding", None) or {}).keys()),
        "outputKeys": sorted(output.keys()) if isinstance(output, dict) else [],
        "errorType": getattr(step, "errorType", None),
    }


def _subtask_summary(subtask: Any) -> dict[str, Any]:
    return {
        "subtaskId": getattr(subtask, "subtaskId", None),
        "parentStepId": getattr(subtask, "parentStepId", None),
        "phase": _enum_value(getattr(subtask, "phase", None)),
        "subagentType": _enum_value(getattr(subtask, "subagentType", None)),
        "goal": getattr(subtask, "goal", None),
        "operationId": getattr(subtask, "operationId", None),
        "status": _enum_value(getattr(subtask, "status", None)),
        "resultSummary": getattr(subtask, "resultSummary", None),
        "resultRef": getattr(subtask, "resultRef", None),
        "errorType": getattr(subtask, "errorType", None),
    }


def _unfinished_goals(
    task_run: Any,
    plan_steps: list[Any],
    active_steps: list[Any],
    active_subtasks: list[Any],
) -> list[dict[str, Any]]:
    goals: list[dict[str, Any]] = []
    for item in getattr(task_run, "goalStack", []) or []:
        goals.append(
            {
                "source": "goalStack",
                "goal": getattr(item, "goal", None),
                "phase": _enum_value(getattr(item, "phase", None)),
                "status": "ACTIVE",
            }
        )
    for step in plan_steps:
        status = _enum_value(getattr(step, "status", None))
        if status not in {"SUCCESS", "SKIPPED"}:
            goals.append(
                {
                    "source": "plan",
                    "goal": getattr(step, "goal", None),
                    "phase": None,
                    "status": status,
                    "stepNo": getattr(step, "stepNo", None),
                }
            )
    for step in active_steps:
        goals.append(
            {
                "source": "taskStep",
                "goal": getattr(step, "goal", None),
                "phase": _enum_value(getattr(step, "phase", None)),
                "status": _enum_value(getattr(step, "status", None)),
                "taskStepId": getattr(step, "taskStepId", None),
            }
        )
    for subtask in active_subtasks:
        goals.append(
            {
                "source": "subtask",
                "goal": getattr(subtask, "goal", None),
                "phase": _enum_value(getattr(subtask, "phase", None)),
                "status": _enum_value(getattr(subtask, "status", None)),
                "subtaskId": getattr(subtask, "subtaskId", None),
            }
        )
    return goals[:20]


def _status_counts(items: list[Any]) -> dict[str, int]:
    return dict(Counter(_enum_value(getattr(item, "status", None)) for item in items))


def _resource_summary(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        return value
    allowed_keys = {
        "sceneCode",
        "sceneName",
        "sourceCode",
        "sourceType",
        "sourceName",
        "sysCode",
        "envCode",
        "datasourceCode",
        "versionNo",
        "questionType",
    }
    result = {key: item for key, item in value.items() if key in allowed_keys and _is_scalar(item)}
    for nested_key in ("source", "scene", "contract"):
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            nested_summary = _resource_summary(nested)
            if nested_summary:
                result[nested_key] = nested_summary
    return result


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
