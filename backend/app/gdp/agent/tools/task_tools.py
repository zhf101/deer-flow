"""GDP Task Agent 任务状态工具。"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.gdp.datagen.config.task.service import DatagenTaskService


async def get_datagen_task_state(task_service: DatagenTaskService, task_run_id: str) -> dict[str, Any]:
    """读取造数任务状态摘要。"""

    task_run = await task_service.get_task_run(task_run_id)
    steps = await task_service.list_steps(task_run_id)
    events = await task_service.list_events(task_run_id)
    return {
        "taskRunId": task_run.taskRunId,
        "userIntent": task_run.userIntent,
        "envCode": task_run.envCode,
        "status": task_run.status,
        "phase": task_run.phase,
        "goalStack": [item.model_dump(mode="json") for item in task_run.goalStack],
        "plan": task_run.plan.model_dump(mode="json") if task_run.plan else None,
        "visibleVariables": [
            {
                "name": item.name,
                "source": item.source,
                "semanticType": item.semanticType,
                "label": item.label,
                "valueSchema": item.valueSchema,
                "valuePreview": None if item.sensitive else item.valuePreview,
                "valueSize": item.valueSize.model_dump(mode="json") if item.valueSize else None,
                "sensitive": item.sensitive,
                "confidence": item.confidence,
            }
            for item in task_run.visibleVariables
        ],
        "stepCount": len(steps),
        "recentEvents": [
            {
                "eventType": event.eventType,
                "phase": event.phase,
                "message": event.message,
                "payload": event.payload,
            }
            for event in events[-5:]
        ],
    }


def build_task_tools(task_service: DatagenTaskService) -> list[StructuredTool]:
    """构造 Task 阶段 LangChain 工具。"""

    async def _get_datagen_task_state(task_run_id: str) -> dict[str, Any]:
        """读取造数任务状态摘要。"""

        return await get_datagen_task_state(task_service, task_run_id)

    return [
        StructuredTool.from_function(
            coroutine=_get_datagen_task_state,
            name="get_datagen_task_state",
            description="读取造数任务状态摘要，包括阶段、变量栈摘要、步骤数量和最近事件。",
        )
    ]
