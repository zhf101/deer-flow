"""GDP Agent Runtime Scene 调用适配器。"""

from __future__ import annotations

from typing import Any


async def call_scene(scene_code: str, env_code: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """调用 datagen SceneService 并返回可判定摘要。"""
    from app.gdp.datagen.config.base.repository import BaseConfigRepository
    from app.gdp.datagen.config.scene.executor import SceneExecutor
    from app.gdp.datagen.config.scene.models import SceneRunRequest
    from app.gdp.datagen.config.scene.repository import SceneRepository
    from app.gdp.datagen.config.scene.service import SceneService
    from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
    from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
    from app.gdp.datagen.runtime.sql.service import SqlExecutionService
    from deerflow.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Persistence not available")

    base_repository = BaseConfigRepository(session_factory)
    sql_execution = SqlExecutionService(
        base_repository=base_repository,
        sql_source_repository=SqlSourceRepository(session_factory),
        registry=SqlExecutorRegistry(),
    )
    service = SceneService(
        SceneRepository(session_factory),
        SceneExecutor(sql_execution, base_repository),
    )
    result = await service.run_scene(
        SceneRunRequest(
            sceneCode=scene_code,
            envCode=env_code,
            inputs=inputs,
        )
    )
    return result.model_dump(mode="json")
