"""造数任务控制面校验辅助。"""

from __future__ import annotations

from app.gdp.datagen.config.task.models import DatagenTaskRunCreateRequest


def normalize_task_intent(request: DatagenTaskRunCreateRequest) -> DatagenTaskRunCreateRequest:
    """清理用户任务目标两端空白。"""

    return request.model_copy(update={"userIntent": request.userIntent.strip()})
