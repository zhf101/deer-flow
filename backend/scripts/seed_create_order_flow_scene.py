# -*- coding: utf-8 -*-
"""为 GDP 造数系统配置“创建订单 -> 支付订单 -> 查询订单状态”的三步验证流场景。

运行方式:
    PYTHONPATH=. uv run python scripts/seed_create_order_flow_scene.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.gdp.datagen.config.common.models import (
    CapabilitySideEffect,
    CapabilityType,
    ConditionRule,
    HttpMethod,
    InputFieldDefinition,
    InputFieldType,
    ResponseConditionGroup,
    ResponseHandling,
    SceneStatus,
    SceneSuccessCriteria,
)
from app.gdp.datagen.config.scene.models import HttpStepDefinition, SceneDefinition
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

HTTP_SYS_CODE = "SYS_HTTP_TEST"
OPERATOR = "gdp-order-flow-seed"


def side_effect(effect_type: str, target: str | None = None, description: str | None = None) -> CapabilitySideEffect:
    """构造副作用对象。"""
    return CapabilitySideEffect(effectType=effect_type, target=target, description=description)


def success_response_handling() -> ResponseHandling:
    """标准成功响应处理：状态码200 + success=true。"""
    return ResponseHandling(
        expectedContentType="JSON",
        statusCode={"success": [200]},
        businessSuccess={"allOf": [{"path": "${RES_BODY(success)}", "op": "EQ", "value": True}]},
        businessFailure={"anyOf": [{"path": "${RES_BODY(success)}", "op": "EQ", "value": False}]},
    )


def json_request_mapping(body: dict[str, Any]) -> dict[str, Any]:
    """构造当前 HTTP 执行器支持的 JSON 请求体配置。"""
    return {
        "headers": {"Accept": "application/json", "Content-Type": "application/json"},
        "bodyType": "raw-json",
        "rawBody": json.dumps(body, ensure_ascii=False),
    }


def build_three_step_flow_scene() -> SceneDefinition:
    """构建创建订单 -> 支付订单 -> 查询订单状态三步流的场景定义。"""
    
    # 步骤列表
    steps = [
        # 步骤 1：创建待支付订单
        HttpStepDefinition(
            stepId="create_order",
            stepName="第一步：创建待支付订单",
            type="HTTP",
            executionOrder=1,
            sysCode=HTTP_SYS_CODE,
            method=HttpMethod.POST,
            path="/api/v1/orders/pending",
            requestMapping=json_request_mapping({
                "buyer_id": "${input.buyer_id}",
                "amount": "${input.amount}",
            }),
            responseHandling=success_response_handling(),
            outputMapping={
                "order_id": "${RES_BODY(data.order_id)}",
                "pay_status": "${RES_BODY(data.pay_status)}",
            },
        ),
        # 步骤 2：发起支付
        HttpStepDefinition(
            stepId="pay_order",
            stepName="第二步：发起支付",
            type="HTTP",
            executionOrder=2,
            dependsOn=["create_order"],
            sysCode=HTTP_SYS_CODE,
            method=HttpMethod.POST,
            path="/api/v1/payments",
            requestMapping=json_request_mapping({
                "order_id": "${steps.create_order.outputs.order_id}",
                "payment_method": "${input.payment_method}",
            }),
            responseHandling=success_response_handling(),
            outputMapping={
                "payment_id": "${RES_BODY(data.payment_id)}",
                "status": "${RES_BODY(data.status)}",
            },
        ),
        # 步骤 3：查询支付状态
        HttpStepDefinition(
            stepId="query_status",
            stepName="第三步：查询支付状态",
            type="HTTP",
            executionOrder=3,
            dependsOn=["pay_order"],
            sysCode=HTTP_SYS_CODE,
            method=HttpMethod.GET,
            path="/api/v1/payments/${steps.create_order.outputs.order_id}/status",
            requestMapping={
                "headers": {"Accept": "application/json"},
            },
            responseHandling=success_response_handling(),
            outputMapping={
                "pay_status": "${RES_BODY(data.pay_status)}",
                "paid_at": "${RES_BODY(data.paid_at)}",
            },
        ),
    ]

    return SceneDefinition(
        sceneCode="create_pay_query_order_flow",
        sceneName="创建支付及查询订单三步流",
        sceneRemark="一键完成创建待支付订单、发起支付和最终查询状态的三步闭环验证流",
        tags=["订单", "支付", "查询", "三步流", "验证"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            side_effect("CREATE_ORDER", "trade_order", "创建订单记录"),
            side_effect("MODIFY_PAYMENT", "payment_record", "创建支付记录"),
            side_effect("MODIFY_ACCOUNT", "user_account", "扣减账户余额"),
        ],
        agentDescription="一键完成订单创建、支付、状态查询的三步验证流场景，用于测试交易支付链路的完整闭环，最终验证支付状态是否为已支付（PAID）",
        inputSchema=[
            InputFieldDefinition(
                name="buyer_id",
                type=InputFieldType.STRING,
                required=True,
                defaultValue="U10001",
                label="买家 ID",
                remark="下单的买家用户 ID",
            ),
            InputFieldDefinition(
                name="amount",
                type=InputFieldType.NUMBER,
                required=True,
                defaultValue=100.0,
                label="订单金额",
                remark="订单的支付金额",
            ),
            InputFieldDefinition(
                name="payment_method",
                type=InputFieldType.STRING,
                required=True,
                defaultValue="ALIPAY",
                label="支付方式",
                remark="支付渠道，如 ALIPAY、WECHAT",
            ),
        ],
        steps=steps,
        resultMapping={
            "order_id": "${steps.create_order.outputs.order_id}",
            "payment_id": "${steps.pay_order.outputs.payment_id}",
            "pay_status": "${steps.query_status.outputs.pay_status}",
        },
        successCriteria=SceneSuccessCriteria(
            enabled=True,
            businessSuccess=ResponseConditionGroup(
                allOf=[
                    ConditionRule(path="pay_status", op="EQ", value="PAID")
                ],
                anyOf=[],
            ),
            businessFailure=ResponseConditionGroup(
                allOf=[],
                anyOf=[
                    ConditionRule(path="pay_status", op="NE", value="PAID")
                ],
            ),
        ),
        status=SceneStatus.DRAFT,
    )


async def seed() -> None:
    print("=" * 60)
    print("开始配置订单三步流验证场景...")
    print("=" * 60)

    app_config = get_app_config()
    await init_engine_from_config(app_config.database)
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("数据库引擎初始化失败，无法写入配置。")

    service = SceneService(SceneRepository(session_factory))
    definition = build_three_step_flow_scene()
    scene_code = definition.sceneCode

    # 1. 写入或更新草稿
    try:
        await service.update_scene(scene_code, definition, operator=OPERATOR)
        print("  [OK] 场景已存在，更新草稿成功。")
    except Exception as e:
        if "not found" in str(e).lower() or "不存在" in str(e):
            await service.create_scene(definition, operator=OPERATOR)
            print("  [OK] 场景不存在，创建草稿成功。")
        else:
            raise

    # 2. 发布场景
    print(f"  发布场景 {scene_code} 到已发布状态...")
    await service.publish_scene(scene_code, operator=OPERATOR)
    print("  [OK] 场景发布成功。")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(seed())
    finally:
        asyncio.run(close_engine())
