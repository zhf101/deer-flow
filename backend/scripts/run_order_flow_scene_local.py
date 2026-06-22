# -*- coding: utf-8 -*-
"""在本地直接调用 SceneService 运行“订单创建支付状态查询三步流”场景，绕过 HTTP API 的 CSRF 检验。

运行方式:
    PYTHONPATH=. .venv/Scripts/python.exe scripts/run_order_flow_scene_local.py
"""

from __future__ import annotations

import asyncio
import json
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.scene.executor import SceneExecutor
from app.gdp.datagen.config.scene.models import SceneRunRequest
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.runtime.sql.registry import SqlExecutorRegistry
from app.gdp.datagen.runtime.sql.service import SqlExecutionService
from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config


async def run_local() -> None:
    app_config = get_app_config()
    await init_engine_from_config(app_config.database)
    sf = get_session_factory()
    if sf is None:
        raise RuntimeError("数据库引擎初始化失败")

    base_repository = BaseConfigRepository(sf)
    sql_execution = SqlExecutionService(
        base_repository=base_repository,
        sql_source_repository=SqlSourceRepository(sf),
        registry=SqlExecutorRegistry(),
    )
    service = SceneService(SceneRepository(sf), SceneExecutor(sql_execution, base_repository))

    request = SceneRunRequest(
        sceneCode="create_pay_query_order_flow",
        envCode="dev",
        inputs={
            "buyer_id": "U10001",
            "amount": 100.0,
            "payment_method": "ALIPAY"
        }
    )

    print("=" * 60)
    print(f"开始本地执行场景: {request.sceneCode}")
    print("=" * 60)

    try:
        result = await service.run_scene(request)
        print("场景执行完成！")
        print(f"整体状态: {result.status}")
        print(f"总耗时: {result.durationMs:.2f} ms")
        print("\n最终输出变量 (finalOutput):")
        print(json.dumps(result.finalOutput, ensure_ascii=False, indent=2))
        
        print("\n业务成功判定 (businessResult):")
        if result.businessResult:
            print(f"  是否成功: {result.businessResult.isSuccess}")
            print(f"  说明: {result.businessResult.reason}")
            print(f"  命中成功规则: {result.businessResult.matchedRules}")
            print(f"  命中失败规则: {result.businessResult.failedRules}")
        else:
            print("  未配置业务判定")
            
        print("\n步骤执行详情:")
        for step in result.stepResults:
            print(f"  - 步骤 ID: {step.stepId} ({step.stepName})")
            print(f"    状态: {step.status}")
            print(f"    耗时: {step.durationMs:.2f} ms")
            if step.error:
                print(f"    错误信息: {step.error}")
            print(f"    输出变量: {step.outputs}")
            print(f"    原始响应摘要: {step.rawResponse}")
            print("-" * 40)
            
    except Exception as e:
        print(f"执行时发生异常: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(run_local())
    finally:
        asyncio.run(close_engine())
