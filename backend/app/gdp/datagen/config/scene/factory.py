"""场景执行服务装配工厂。

业务目标：消除 SceneService 依赖链在多个调用方（运行时适配器、HTTP 路由）
中重复组装的问题，确保「改一处不必改两处」。
当前动作：build_scene_service() 接收已校验非空的 session_factory，
统一组装 BaseConfigRepository → SqlExecutionService → SceneService(SceneExecutor)。
预期结果：所有需要 SceneService 的调用方共用同一装配逻辑；
调用方各自负责 session_factory 的获取与不可用时的错误语义。
"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.scene.executor import SceneExecutor
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService


def build_scene_service(session_factory: Any) -> SceneService:
    """组装完整的 SceneService 依赖链。

    业务目标：让造数场景执行能力的装配只有一处定义，
    供运行时引擎适配器和场景管理 HTTP 路由共用。
    当前动作：用传入的 session_factory 构造基础配置仓库、SQL 执行服务、
    场景仓库与场景执行器，返回可执行 run_scene 的 SceneService。
    预期结果：返回装配完成的 SceneService；
    调用方需保证 session_factory 非空（不可用时的报错语义由调用方决定）。
    """
    base_repository = BaseConfigRepository(session_factory)
    sql_execution = SqlExecutionService(
        base_repository=base_repository,
        sql_source_repository=SqlSourceRepository(session_factory),
        registry=SqlExecutorRegistry(),
    )
    return SceneService(
        SceneRepository(session_factory),
        SceneExecutor(sql_execution, base_repository),
    )
