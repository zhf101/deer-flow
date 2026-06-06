"""造数任务业务逻辑层。"""

from __future__ import annotations

from fastapi import HTTPException

from app.gdp.datagen.scene.models import SceneDefinition
from app.gdp.datagen.scene.repository import SceneRepository
from app.gdp.datagen.task.models import (
    TaskDefinition,
    TaskSummary,
    TaskValidationResult,
    TaskVersion,
)
from app.gdp.datagen.task.repository import (
    TaskConflictError,
    TaskNotFoundError,
    TaskRepository,
)
from app.gdp.datagen.task.validation import validate_task_draft, validate_task_publish
from app.gdp.models import SceneStatus


class TaskService:
    def __init__(self, task_repo: TaskRepository, scene_repo: SceneRepository) -> None:
        self._task_repo = task_repo
        self._scene_repo = scene_repo

    async def list_tasks(
        self, *, keyword: str | None = None, status: SceneStatus | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[TaskSummary]:
        return await self._task_repo.list_tasks(keyword=keyword, status=status, limit=limit, offset=offset)

    async def create_task(self, definition: TaskDefinition, *, operator: str | None = None) -> TaskVersion:
        result = validate_task_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._task_repo.create_task(definition, operator=operator))

    async def get_task(self, task_code: str) -> TaskDefinition:
        return await self._guard(lambda: self._task_repo.get_task_definition(task_code))

    async def update_task(self, task_code: str, definition: TaskDefinition, *, operator: str | None = None) -> TaskVersion:
        result = validate_task_draft(definition)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._task_repo.update_task(task_code, definition, operator=operator))

    async def validate_task(self, task_code: str) -> TaskValidationResult:
        task = await self._guard(lambda: self._task_repo.get_task_definition(task_code))
        scenes = await self._published_scenes_by_code(task)
        return validate_task_publish(task, scenes_by_code=scenes)

    async def publish_task(self, task_code: str, *, operator: str | None = None) -> TaskVersion:
        task = await self._guard(lambda: self._task_repo.get_task_definition(task_code))
        scenes = await self._published_scenes_by_code(task)
        result = validate_task_publish(task, scenes_by_code=scenes)
        if not result.valid:
            raise HTTPException(status_code=422, detail=result.model_dump(mode="json"))
        return await self._guard(lambda: self._task_repo.publish_task(task_code, result, operator=operator))

    async def disable_task(self, task_code: str, *, operator: str | None = None) -> bool:
        return await self._guard(lambda: self._task_repo.disable_task(task_code, operator=operator))

    async def delete_task(self, task_code: str, *, operator: str | None = None) -> bool:
        return await self._guard(lambda: self._task_repo.delete_task(task_code, operator=operator))

    async def list_task_versions(self, task_code: str) -> list[TaskVersion]:
        return await self._guard(lambda: self._task_repo.list_task_versions(task_code))

    # ---------- 内部辅助 ----------

    async def _published_scenes_by_code(self, task: TaskDefinition) -> dict[str, SceneDefinition]:
        result: dict[str, SceneDefinition] = {}
        for step in task.steps:
            if step.sceneCode and step.sceneCode not in result:
                try:
                    scene = await self._scene_repo.get_scene_definition(step.sceneCode)
                    result[step.sceneCode] = scene
                except Exception:
                    pass  # 校验阶段会发现缺失的场景
        return result

    async def _guard(self, call):
        try:
            return await call()
        except TaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TaskConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
