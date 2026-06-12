"""为 GDP Agent 第二阶段测试创建场景配置。

运行方式:
    PYTHONPATH=. uv run python scripts/seed_gdp_agent_test_scenes.py
    PYTHONPATH=. uv run python scripts/seed_gdp_agent_test_scenes.py --dry-run  # 预览不写库
"""

from __future__ import annotations

import argparse
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
OPERATOR = "gdp-agent-test-seed"


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


def scene_success_criteria(
    path: str,
    op: str = "NOT_EMPTY",
    value: Any = None,
    *,
    failure_path: str | None = None,
    failure_op: str = "EQ",
    failure_value: Any = None,
) -> SceneSuccessCriteria:
    """构造场景级业务成功/失败判定。"""

    success_rule = ConditionRule(path=path, op=op, value=value)
    failure_rules = []
    if failure_path is not None:
        failure_rules.append(ConditionRule(path=failure_path, op=failure_op, value=failure_value))
    return SceneSuccessCriteria(
        enabled=True,
        businessSuccess=ResponseConditionGroup(allOf=[success_rule], anyOf=[]),
        businessFailure=ResponseConditionGroup(allOf=[], anyOf=failure_rules),
    )


def json_request_mapping(body: dict[str, Any]) -> dict[str, Any]:
    """构造当前 HTTP 执行器支持的 JSON 请求体配置。"""

    return {
        "headers": {"Accept": "application/json", "Content-Type": "application/json"},
        "bodyType": "raw-json",
        "rawBody": json.dumps(body, ensure_ascii=False),
    }


def step_output(name: str) -> str:
    """引用单步骤测试场景的输出变量。"""

    return f"${{steps.step-1.outputs.{name}}}"


def build_test_scenes() -> list[SceneDefinition]:
    """构建 GDP Agent 测试场景集。"""
    scenes = []

    # ===== 场景1: create_pending_order =====
    scenes.append(
        SceneDefinition(
            sceneCode="create_pending_order",
            sceneName="创建待支付订单",
            sceneRemark="创建待支付状态的订单，等待后续支付",
            tags=["订单", "待支付", "创建订单", "造数"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="交易",
            sideEffects=[side_effect("CREATE_ORDER", "trade_order", "创建订单记录")],
            agentDescription="创建待支付状态的订单，支付状态为 PENDING，适用于测试支付前订单状态",
            inputSchema=[
                InputFieldDefinition(name="buyer_id", type=InputFieldType.STRING, required=True, description="买家用户ID"),
                InputFieldDefinition(name="amount", type=InputFieldType.NUMBER, required=True, description="订单金额"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="调用创建待支付订单接口",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/orders/pending",
                    requestMapping=json_request_mapping(
                        {
                            "buyer_id": "${input.buyer_id}",
                            "amount": "${input.amount}",
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "order_id": "${RES_BODY(data.order_id)}",
                        "pay_status": "${RES_BODY(data.pay_status)}",
                    },
                )
            ],
            resultMapping={"order_id": step_output("order_id"), "pay_status": step_output("pay_status")},
            successCriteria=scene_success_criteria(
                "pay_status",
                "EQ",
                "PENDING",
                failure_path="pay_status",
                failure_op="NOT_IN",
                failure_value=["PENDING"],
            ),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景2: create_order_with_items =====
    scenes.append(
        SceneDefinition(
            sceneCode="create_order_with_items",
            sceneName="创建带商品订单",
            sceneRemark="创建包含商品明细的订单，同时锁定库存",
            tags=["订单", "商品", "下单", "购物", "造数"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="交易",
            sideEffects=[
                side_effect("CREATE_ORDER", "trade_order", "创建订单记录"),
                side_effect("MODIFY_INVENTORY", "inventory", "锁定商品库存"),
            ],
            agentDescription="创建包含商品明细的订单，同时锁定库存数量，适用于测试完整下单流程",
            inputSchema=[
                InputFieldDefinition(name="buyer_id", type=InputFieldType.STRING, required=True, description="买家用户ID"),
                InputFieldDefinition(name="product_id", type=InputFieldType.STRING, required=True, description="商品ID"),
                InputFieldDefinition(name="quantity", type=InputFieldType.NUMBER, required=True, description="购买数量"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="创建带商品订单",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/orders/with-items",
                    requestMapping=json_request_mapping(
                        {
                            "buyer_id": "${input.buyer_id}",
                            "product_id": "${input.product_id}",
                            "quantity": "${input.quantity}",
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "order_id": "${RES_BODY(data.order_id)}",
                        "inventory_locked": "${RES_BODY(data.inventory_locked)}",
                    },
                )
            ],
            resultMapping={"order_id": step_output("order_id"), "inventory_locked": step_output("inventory_locked")},
            successCriteria=scene_success_criteria(
                "inventory_locked",
                "EQ",
                True,
                failure_path="inventory_locked",
                failure_op="EQ",
                failure_value=False,
            ),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景3: create_payment（有副作用，需审批）=====
    scenes.append(
        SceneDefinition(
            sceneCode="create_payment",
            sceneName="发起支付",
            sceneRemark="对指定订单发起支付，扣减用户账户余额",
            tags=["支付", "付款", "扣款", "资金"],
            capabilityType=CapabilityType.UPDATE,
            businessDomain="支付",
            sideEffects=[
                side_effect("MODIFY_PAYMENT", "payment_record", "创建支付记录"),
                side_effect("MODIFY_ACCOUNT", "user_account", "扣减账户余额"),
            ],
            agentDescription="对指定订单发起支付操作，从用户账户扣款，涉及资金变动需确认",
            inputSchema=[
                InputFieldDefinition(name="order_id", type=InputFieldType.STRING, required=True, description="订单ID"),
                InputFieldDefinition(name="payment_method", type=InputFieldType.STRING, required=True, description="支付方式"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="调用支付接口",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/payments",
                    requestMapping=json_request_mapping(
                        {
                            "order_id": "${input.order_id}",
                            "payment_method": "${input.payment_method}",
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "payment_id": "${RES_BODY(data.payment_id)}",
                        "status": "${RES_BODY(data.status)}",
                    },
                )
            ],
            resultMapping={"payment_id": step_output("payment_id"), "status": step_output("status")},
            successCriteria=scene_success_criteria(
                "status",
                "EQ",
                "SUCCESS",
                failure_path="status",
                failure_op="NOT_IN",
                failure_value=["SUCCESS"],
            ),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景4: query_payment_status（无副作用）=====
    scenes.append(
        SceneDefinition(
            sceneCode="query_payment_status",
            sceneName="查询支付状态",
            sceneRemark="查询订单的支付状态和支付流水",
            tags=["支付", "查询", "状态"],
            capabilityType=CapabilityType.QUERY,
            businessDomain="支付",
            sideEffects=[],  # 无副作用
            agentDescription="查询订单当前的支付状态，纯查询操作无副作用",
            inputSchema=[
                InputFieldDefinition(name="order_id", type=InputFieldType.STRING, required=True, description="订单ID"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="查询支付状态",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.GET,
                    path="/api/v1/payments/${input.order_id}/status",
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "pay_status": "${RES_BODY(data.pay_status)}",
                        "paid_at": "${RES_BODY(data.paid_at)}",
                    },
                )
            ],
            resultMapping={"pay_status": step_output("pay_status"), "paid_at": step_output("paid_at")},
            successCriteria=scene_success_criteria(
                "pay_status",
                "EQ",
                "PAID",
                failure_path="pay_status",
                failure_op="NOT_IN",
                failure_value=["PAID"],
            ),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景5: create_user_profile（多必填参数）=====
    scenes.append(
        SceneDefinition(
            sceneCode="create_user_profile",
            sceneName="创建用户档案",
            sceneRemark="创建新用户档案，包含基本信息和联系方式",
            tags=["用户", "注册", "创建"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="用户",
            sideEffects=[side_effect("CREATE_USER", "user_profile", "创建用户档案")],
            agentDescription="创建新用户档案，需要提供用户名、手机号、邮箱等完整信息",
            inputSchema=[
                InputFieldDefinition(name="username", type=InputFieldType.STRING, required=True, description="用户名"),
                InputFieldDefinition(name="phone", type=InputFieldType.STRING, required=True, description="手机号"),
                InputFieldDefinition(name="email", type=InputFieldType.STRING, required=True, description="邮箱地址"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="创建用户",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/users",
                    requestMapping=json_request_mapping(
                        {
                            "user": {
                                "name": "${input.username}",
                                "phone": "${input.phone}",
                                "email": "${input.email}",
                            }
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "user_id": "${RES_BODY(data.userId)}",
                    },
                )
            ],
            resultMapping={"user_id": step_output("user_id")},
            successCriteria=scene_success_criteria("user_id"),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景6: rare_refund_order（零候选场景）=====
    scenes.append(
        SceneDefinition(
            sceneCode="rare_refund_order",
            sceneName="订单退款",
            sceneRemark="处理订单退款，退回支付金额到用户账户",
            tags=["退款", "退单"],  # 注意：无"订单"标签，触发零候选
            capabilityType=CapabilityType.UPDATE,
            businessDomain="交易",
            sideEffects=[
                side_effect("MODIFY_ORDER", "trade_order", "更新订单状态为已退款"),
                side_effect("MODIFY_PAYMENT", "payment_record", "创建退款记录"),
            ],
            agentDescription="处理订单退款申请，退回支付金额到用户账户，涉及资金操作",
            inputSchema=[
                InputFieldDefinition(name="order_id", type=InputFieldType.STRING, required=True, description="订单ID"),
                InputFieldDefinition(name="refund_amount", type=InputFieldType.NUMBER, required=True, description="退款金额"),
                InputFieldDefinition(name="refund_reason", type=InputFieldType.STRING, required=True, description="退款原因"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="提交退款申请",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/orders/${input.order_id}/refund",
                    requestMapping=json_request_mapping(
                        {
                            "refund_amount": "${input.refund_amount}",
                            "refund_reason": "${input.refund_reason}",
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "refund_id": "${RES_BODY(data.refund_id)}",
                        "status": "${RES_BODY(data.status)}",
                    },
                )
            ],
            resultMapping={"refund_id": step_output("refund_id"), "status": step_output("status")},
            successCriteria=scene_success_criteria(
                "status",
                "EQ",
                "REFUNDED",
                failure_path="status",
                failure_op="NOT_IN",
                failure_value=["REFUNDED"],
            ),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景7: intentional_fail_order（黑名单测试）=====
    scenes.append(
        SceneDefinition(
            sceneCode="intentional_fail_order",
            sceneName="创建订单（故意失败）",
            sceneRemark="测试用订单创建场景，会故意返回失败",
            tags=["订单", "创建", "测试"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="交易",
            sideEffects=[side_effect("CREATE_ORDER", "trade_order", "创建订单记录")],
            agentDescription="测试用场景，当 buyer_id 为 FAIL_USER 时故意失败，用于验证黑名单机制",
            inputSchema=[
                InputFieldDefinition(name="buyer_id", type=InputFieldType.STRING, required=True, description="买家用户ID"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="创建订单（测试失败）",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/orders/fail",
                    requestMapping=json_request_mapping({"buyer_id": "${input.buyer_id}"}),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "order_id": "${RES_BODY(data.order_id)}",
                    },
                )
            ],
            resultMapping={"order_id": step_output("order_id")},
            successCriteria=scene_success_criteria("order_id"),
            status=SceneStatus.DRAFT,
        )
    )

    # ===== 场景8: lock_inventory（副作用审批）=====
    scenes.append(
        SceneDefinition(
            sceneCode="lock_inventory",
            sceneName="锁定库存",
            sceneRemark="为订单锁定商品库存，防止超卖",
            tags=["库存", "锁定", "预占"],
            capabilityType=CapabilityType.UPDATE,
            businessDomain="库存",
            sideEffects=[side_effect("MODIFY_INVENTORY", "inventory", "锁定商品库存数量")],
            agentDescription="为订单锁定商品库存，防止超卖",
            inputSchema=[
                InputFieldDefinition(name="product_id", type=InputFieldType.STRING, required=True, description="商品ID"),
                InputFieldDefinition(name="quantity", type=InputFieldType.NUMBER, required=True, description="锁定数量"),
            ],
            steps=[
                HttpStepDefinition(
                    stepId="step-1",
                    stepName="锁定库存",
                    type="HTTP",
                    executionOrder=1,
                    sysCode=HTTP_SYS_CODE,
                    method=HttpMethod.POST,
                    path="/api/v1/inventory/lock",
                    requestMapping=json_request_mapping(
                        {
                            "product_id": "${input.product_id}",
                            "quantity": "${input.quantity}",
                        }
                    ),
                    responseHandling=success_response_handling(),
                    outputMapping={
                        "lock_id": "${RES_BODY(data.lock_id)}",
                    },
                )
            ],
            resultMapping={"lock_id": step_output("lock_id")},
            successCriteria=scene_success_criteria("lock_id"),
            status=SceneStatus.DRAFT,
        )
    )

    return scenes


async def upsert_scene(service: SceneService, definition: SceneDefinition, dry_run: bool = False) -> None:
    """插入或更新场景（创建草稿）。"""
    scene_code = definition.sceneCode
    print(f"[{scene_code}] 准备写入场景: {definition.sceneName}")

    if dry_run:
        print("  [DRY-RUN] 跳过实际写入")
        print(f"  - 标签: {definition.tags}")
        print(f"  - 能力: {definition.capabilityType.value}")
        print(f"  - 副作用: {[e.effectType for e in definition.sideEffects]}")
        print(f"  - 必填参数: {[f.name for f in definition.inputSchema if f.required]}")
        criteria = definition.successCriteria
        print(f"  - 场景级业务判定: {'启用' if criteria and criteria.enabled else '未启用'}")
        if criteria:
            print(f"    成功规则: {len(criteria.businessSuccess.allOf)} 条")
            print(f"    失败规则: {len(criteria.businessFailure.anyOf)} 条")
        return

    try:
        # 尝试更新
        await service.update_scene(scene_code, definition, operator=OPERATOR)
        print("  场景已存在，更新为新版本...")
        print("  [OK] 更新成功")
    except Exception as e:
        if "not found" in str(e).lower() or "不存在" in str(e):
            # 场景不存在，创建新场景
            print("  场景不存在，创建新场景...")
            await service.create_scene(definition, operator=OPERATOR)
            print("  [OK] 创建成功")
        else:
            # 其他错误，重新抛出
            raise


async def publish_scene(service: SceneService, scene_code: str, dry_run: bool = False) -> None:
    """发布场景到 PUBLISHED 状态。"""
    if dry_run:
        print(f"[{scene_code}] [DRY-RUN] 跳过发布")
        return

    print(f"[{scene_code}] 发布场景...")
    try:
        await service.publish_scene(scene_code, operator=OPERATOR)
        print("  [OK] 发布成功")
    except Exception as e:
        print(f"  [WARN] 发布失败: {e}")


async def seed(dry_run: bool = False) -> None:
    """写入测试场景集。"""
    print("=" * 60)
    print("GDP Agent 第二阶段测试场景配置")
    print(f"模式: {'预览（不写库）' if dry_run else '实际写入'}")
    print("=" * 60)

    if not dry_run:
        app_config = get_app_config()
        await init_engine_from_config(app_config.database)
        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeError("数据库未初始化，无法写入场景配置")

        scene_service = SceneService(SceneRepository(session_factory))
    else:
        scene_service = None  # type: ignore

    scenes = build_test_scenes()
    print(f"\n共 {len(scenes)} 个场景待写入:\n")

    for scene in scenes:
        await upsert_scene(scene_service, scene, dry_run=dry_run)  # type: ignore
        print()

    if not dry_run:
        print("\n" + "=" * 60)
        print("发布场景到 PUBLISHED 状态...")
        print("=" * 60)
        for scene in scenes:
            await publish_scene(scene_service, scene.sceneCode, dry_run=dry_run)  # type: ignore

    print("\n" + "=" * 60)
    print("[OK] 场景配置完成！")
    print("=" * 60)
    print("\n下一步:")
    print("1. 在前端 http://localhost:2026/gdp/datagen/scene 查看场景配置")
    print("2. 启动 Mock Server: python scripts/datagen_http_mock_server.py --sync-endpoints")
    print("3. 扩展 Mock Server 接口（参考 docs/20260612/gdp_agent_test_scenarios_design.md）")
    print("4. 运行测试: uv run pytest tests/test_gdp_agent_runtime_scene_selection_runner.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="为 GDP Agent 第二阶段创建测试场景")
    parser.add_argument("--dry-run", action="store_true", help="预览场景配置，不实际写库")
    args = parser.parse_args()

    try:
        asyncio.run(seed(dry_run=args.dry_run))
    finally:
        asyncio.run(close_engine())


if __name__ == "__main__":
    main()
