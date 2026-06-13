"""场景调用适配器——连接运行时引擎和已有的造数场景执行服务。

业务目标：作为运行时引擎与 datagen 场景执行系统之间的桥梁，
让用户的造数需求通过调用已发布的造数场景来真正执行（如创建订单、发起支付）。
当前动作：call_scene() 组装 SceneService 依赖链并调用 runScene，
返回包含执行状态、业务结果和输出数据的结构化响应。
预期结果：运行时引擎拿到场景执行结果后，交给证据链进行判定。
"""

from __future__ import annotations

from typing import Any


async def call_scene(scene_code: str, env_code: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """执行用户选定的造数场景，真正生成测试数据。

    业务目标：将用户的造数需求转化为对已发布场景的实际调用，
    在指定环境中执行造数操作（如创建订单、生成支付记录等）。
    当前动作：组装 SceneService 依赖链（SQL执行器、基础配置、场景仓库），
    构造 SceneRunRequest 并调用 runScene，获取执行结果。
    预期结果：返回包含执行状态（SUCCESS/BUSINESS_FAILED/EXCEPTION）、
    业务结果和输出数据的结构化响应，供证据链判定造数是否成功。
    """
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
