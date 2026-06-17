"""GDP 造数系统基础模拟数据种子脚本。

一次性初始化所有 datagen 基础配置数据，包括：
1. 系统配置（df_system）
2. 环境配置（df_environment）
3. HTTP 服务端点（df_service_endpoint）
4. 数据库数据源（df_datasource）
5. HTTP 接口配置（df_http_source）— 对应 datagen_http_mock_server.py 的路由
6. SQL 配置（df_sql_source）— 对应 datagen_mock_sqlite.py 的 SQLite 表
7. 标识引用配置（df_identifier_reference）
8. Mock SQLite 业务数据库（member_account / product_sku / inventory / trade_order / order_log）

运行方式:
    cd backend
    PYTHONPATH=. uv run python scripts/seed_gdp_mock_data.py
    PYTHONPATH=. uv run python scripts/seed_gdp_mock_data.py --dry-run      # 预览不写库
    PYTHONPATH=. uv run python scripts/seed_gdp_mock_data.py --http-only     # 只写 HTTP 相关
    PYTHONPATH=. uv run python scripts/seed_gdp_mock_data.py --sql-only      # 只写 SQL 相关
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    EnvironmentConfig,
    IdentifierReferenceConfig,
    IdentifierReferenceExample,
    IdentifierReferenceParameter,
    ServiceEndpointConfig,
    SysConfig,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.base.service import BaseConfigService
from app.gdp.datagen.config.common.models import (
    CapabilitySideEffect,
    CapabilityType,
    ConfigStatus,
    HttpMethod,
    HttpTimeoutConfig,
    InputFieldDefinition,
    InputFieldType,
    ResponseConditionGroup,
    ResponseHandling,
    SqlOperation,
    SqlSourceSafety,
)
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig, SqlSourceParameter
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

# ============================================================
# 常量
# ============================================================

OPERATOR = "gdp-mock-seed"
HTTP_SYS_CODE = "SYS_HTTP_TEST"
SQL_SYS_CODE = "mockTrade"
MOCK_HTTP_BASE_URL = "http://127.0.0.1:18080"

# Mock SQLite 数据库输出路径
DEFAULT_MOCK_DB_DIR = Path(__file__).resolve().parents[1] / ".deer-flow/datagen/mock"


# ============================================================
# 工具函数
# ============================================================


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _success_response_handling() -> ResponseHandling:
    """标准 JSON 成功响应判定：状态码 200 + success=true。"""
    return ResponseHandling(
        expectedContentType="JSON",
        statusCode={"success": [200]},
        businessSuccess=ResponseConditionGroup(
            allOf=[{"path": "${RES_BODY(success)}", "op": "EQ", "value": True}],
        ),
        businessFailure=ResponseConditionGroup(
            anyOf=[{"path": "${RES_BODY(success)}", "op": "EQ", "value": False}],
        ),
    )


def _json_request_mapping(body: dict[str, Any]) -> dict[str, Any]:
    """构造 JSON 请求体映射。"""
    return {
        "headers": {"Accept": "application/json", "Content-Type": "application/json"},
        "bodyType": "raw-json",
        "rawBody": _dumps(body),
    }


# ============================================================
# 1. 系统配置
# ============================================================


def build_systems() -> list[SysConfig]:
    return [
        SysConfig(
            sysCode=HTTP_SYS_CODE,
            sysName="HTTP Mock 测试系统",
            status=ConfigStatus.ENABLED,
            remark="本地 HTTP Mock 服务器（datagen_http_mock_server.py），提供各类 HTTP 接口用于造数测试。",
        ),
        SysConfig(
            sysCode=SQL_SYS_CODE,
            sysName="Mock 交易系统",
            status=ConfigStatus.ENABLED,
            remark="本地 SQLite mock 数据源，包含会员、商品、库存、订单等业务表。",
        ),
    ]


# ============================================================
# 2. 环境配置
# ============================================================


def build_environments() -> list[EnvironmentConfig]:
    return [
        EnvironmentConfig(
            envCode="dev",
            envName="开发环境",
            status=ConfigStatus.ENABLED,
            remark="本地开发环境，连接 Mock 服务和 SQLite。",
        ),
        EnvironmentConfig(
            envCode="test",
            envName="测试环境",
            status=ConfigStatus.ENABLED,
            remark="测试环境，复用同一套 Mock 服务。",
        ),
    ]


# ============================================================
# 3. 服务端点配置
# ============================================================


def build_service_endpoints() -> list[ServiceEndpointConfig]:
    return [
        ServiceEndpointConfig(
            envCode="dev",
            sysCode=HTTP_SYS_CODE,
            baseUrl=MOCK_HTTP_BASE_URL,
            status=ConfigStatus.ENABLED,
        ),
        ServiceEndpointConfig(
            envCode="test",
            sysCode=HTTP_SYS_CODE,
            baseUrl=MOCK_HTTP_BASE_URL,
            status=ConfigStatus.ENABLED,
        ),
    ]


# ============================================================
# 4. 数据源配置
# ============================================================


def build_datasources(mock_db_path: Path) -> list[DatasourceConfig]:
    db_path_str = str(mock_db_path).replace("\\", "/")
    return [
        DatasourceConfig(
            envCode="dev",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            datasourceName="Mock 交易 SQLite",
            dbType="SQLite",
            host="localhost",
            port=1,
            databaseName=db_path_str,
            username="",
            password="",
            status=ConfigStatus.ENABLED,
        ),
        DatasourceConfig(
            envCode="test",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            datasourceName="Mock 交易 SQLite",
            dbType="SQLite",
            host="localhost",
            port=1,
            databaseName=db_path_str,
            username="",
            password="",
            status=ConfigStatus.ENABLED,
        ),
    ]


# ============================================================
# 5. HTTP 接口配置
# ============================================================


def build_http_sources() -> list[HttpSourceConfig]:
    """构建与 datagen_http_mock_server.py 路由对应的 HTTP 接口配置。"""
    sources: list[HttpSourceConfig] = []

    # --- 5.1 GET /api/v1/users ---
    sources.append(HttpSourceConfig(
        sourceCode="httpGetUserList",
        sourceName="查询用户列表",
        tags=["用户", "查询", "列表"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="用户",
        sideEffects=[],
        agentDescription="查询用户列表，支持分页和关键字搜索，返回用户 ID、姓名、年龄、状态等基本信息",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/users",
        method=HttpMethod.GET,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "query": {
                "pageNo": "1",
                "pageSize": "20",
            },
            "headers": {"Accept": "application/json"},
        },
        responseSchema=[
            InputFieldDefinition(name="success", type=InputFieldType.BOOLEAN, label="是否成功"),
            InputFieldDefinition(name="data", type=InputFieldType.OBJECT, label="响应数据"),
            InputFieldDefinition(name="data.total", type=InputFieldType.NUMBER, label="总数"),
            InputFieldDefinition(name="data.list", type=InputFieldType.ARRAY, label="用户列表"),
        ],
        responseHandling=_success_response_handling(),
        outputMapping={
            "total": "${RES_BODY(data.total)}",
            "userList": "${RES_BODY(data.list)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.2 GET /api/v1/accounts/{accountId} ---
    sources.append(HttpSourceConfig(
        sourceCode="httpGetAccountDetail",
        sourceName="查询账户详情",
        tags=["账户", "查询", "详情"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="用户",
        sideEffects=[],
        agentDescription="按账户 ID 查询账户详情，包含姓名、邮箱、手机、部门、角色等完整信息，需要 Bearer Token 认证",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/accounts/${input.accountId}",
        method=HttpMethod.GET,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer ${input.token}",
            },
        },
        responseSchema=[
            InputFieldDefinition(name="success", type=InputFieldType.BOOLEAN, label="是否成功"),
            InputFieldDefinition(name="data.id", type=InputFieldType.STRING, label="账户 ID"),
            InputFieldDefinition(name="data.name", type=InputFieldType.STRING, label="姓名"),
            InputFieldDefinition(name="data.email", type=InputFieldType.STRING, label="邮箱"),
        ],
        responseHandling=_success_response_handling(),
        outputMapping={
            "accountId": "${RES_BODY(data.id)}",
            "name": "${RES_BODY(data.name)}",
            "email": "${RES_BODY(data.email)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.3 GET /openapi/v1/dictionaries ---
    sources.append(HttpSourceConfig(
        sourceCode="httpGetDictionary",
        sourceName="查询字典数据",
        tags=["字典", "查询", "枚举"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="基础",
        sideEffects=[],
        agentDescription="按字典类型查询枚举值列表，支持 USER_STATUS、ORDER_STATUS 等字典类型，使用 API Key 认证",
        sysCode=HTTP_SYS_CODE,
        path="/openapi/v1/dictionaries",
        method=HttpMethod.GET,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "query": {
                "dictType": "${input.dictType}",
                "api_key": "${input.apiKey}",
            },
            "headers": {
                "Accept": "application/json",
                "X-Api-Version": "1.0",
            },
        },
        responseHandling=_success_response_handling(),
        outputMapping={
            "dictType": "${RES_BODY(data.dictType)}",
            "items": "${RES_BODY(data.items)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.4 POST /api/v1/users ---
    sources.append(HttpSourceConfig(
        sourceCode="httpCreateUser",
        sourceName="创建用户",
        tags=["用户", "创建", "注册"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="用户",
        sideEffects=[
            CapabilitySideEffect(effectType="CREATE_USER", target="user", description="创建新用户记录"),
        ],
        agentDescription="创建新用户，需要提供租户 ID、用户姓名、年龄等信息，返回新创建的用户 ID",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/users",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "tenantId": "${input.tenantId}",
            "user": {
                "name": "${input.name}",
                "age": "${input.age}",
                "enabled": True,
            },
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "userId": "${RES_BODY(data.userId)}",
            "name": "${RES_BODY(data.name)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.5 POST /soap/orders/create ---
    sources.append(HttpSourceConfig(
        sourceCode="httpCreateSoapOrder",
        sourceName="创建 SOAP 订单",
        tags=["订单", "创建", "SOAP", "XML"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            CapabilitySideEffect(effectType="CREATE_ORDER", target="order", description="创建 SOAP 订单记录"),
        ],
        agentDescription="通过 SOAP/XML 接口创建订单，使用 Basic Auth 认证，请求体和响应体均为 XML 格式",
        sysCode=HTTP_SYS_CODE,
        path="/soap/orders/create",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "headers": {
                "Content-Type": "application/xml",
                "Accept": "application/xml",
                "Authorization": "Basic ${input.basicAuth}",
            },
            "bodyType": "raw-text",
            "rawBody": (
                '<CreateOrderRequest>'
                '<tenantId>${input.tenantId}</tenantId>'
                '<orderNo>${input.orderNo}</orderNo>'
                '<amount>${input.amount}</amount>'
                '</CreateOrderRequest>'
            ),
        },
        outputMapping={
            "orderId": "${RES_BODY(CreateOrderResponse.orderId)}",
            "orderNo": "${RES_BODY(CreateOrderResponse.orderNo)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.6 POST /api/v1/messages/text ---
    sources.append(HttpSourceConfig(
        sourceCode="httpSendTextMessage",
        sourceName="发送文本消息",
        tags=["消息", "发送", "通知"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="消息",
        sideEffects=[
            CapabilitySideEffect(effectType="SEND_MESSAGE", target="message", description="发送文本消息"),
        ],
        agentDescription="通过纯文本接口发送消息，支持 SMS、EMAIL 等渠道，使用 API Key 认证",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/messages/text",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "query": {"channel": "${input.channel}"},
            "headers": {
                "Content-Type": "text/plain",
                "Accept": "text/plain",
                "X-Api-Key": "${input.apiKey}",
                "X-Tenant-Id": "${input.tenantId}",
            },
            "bodyType": "raw-text",
            "rawBody": "${input.messageText}",
        },
        outputMapping={
            "messageId": "${RES_BODY(messageId)}",
            "status": "${RES_BODY(status)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.7 POST /api/v1/files/upload ---
    sources.append(HttpSourceConfig(
        sourceCode="httpUploadFile",
        sourceName="上传文件",
        tags=["文件", "上传", "附件"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="文件",
        sideEffects=[
            CapabilitySideEffect(effectType="UPLOAD_FILE", target="file", description="上传文件到服务器"),
        ],
        agentDescription="通过 multipart/form-data 上传文件，支持指定上传目录和业务类型，需要 Bearer Token 认证",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/files/upload",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(readTimeoutSeconds=30),
        requestMapping={
            "query": {"folder": "${input.folder}"},
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer ${input.token}",
            },
            "bodyType": "form-data",
            "formFields": {
                "file": "${input.file}",
                "bizType": "${input.bizType}",
            },
        },
        responseHandling=_success_response_handling(),
        outputMapping={
            "fileId": "${RES_BODY(data.fileId)}",
            "fileName": "${RES_BODY(data.fileName)}",
            "downloadUrl": "${RES_BODY(data.downloadUrl)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.8 POST /oauth/token ---
    sources.append(HttpSourceConfig(
        sourceCode="httpOAuthToken",
        sourceName="获取 OAuth Token",
        tags=["认证", "Token", "OAuth", "登录"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="认证",
        sideEffects=[],
        agentDescription="通过 OAuth 客户端凭证模式获取访问令牌，使用 Basic Auth 提交客户端凭证，返回 access_token",
        sysCode=HTTP_SYS_CODE,
        path="/oauth/token",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "headers": {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Authorization": "Basic ${input.clientCredentials}",
            },
            "bodyType": "form-urlencoded",
            "formFields": {
                "grant_type": "password",
                "username": "${input.username}",
                "password": "${input.password}",
                "scope": "${input.scope}",
            },
        },
        outputMapping={
            "access_token": "${RES_BODY(access_token)}",
            "token_type": "${RES_BODY(token_type)}",
            "expires_in": "${RES_BODY(expires_in)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.9 POST /api/v1/session/login ---
    sources.append(HttpSourceConfig(
        sourceCode="httpSessionLogin",
        sourceName="会话登录",
        tags=["认证", "登录", "Session", "Cookie"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="认证",
        sideEffects=[],
        agentDescription="用户会话登录，提交用户名密码，返回 Session ID 和 CSRF Token，同时通过 Set-Cookie 写入会话信息",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/session/login",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "username": "${input.username}",
            "password": "${input.password}",
            "tenantId": "${input.tenantId}",
        }),
        responseCookiesSchema=[
            InputFieldDefinition(name="session_id", type=InputFieldType.STRING, label="会话 ID"),
            InputFieldDefinition(name="csrf_token", type=InputFieldType.STRING, label="CSRF Token"),
        ],
        responseHandling=_success_response_handling(),
        outputMapping={
            "sessionId": "${RES_BODY(data.sessionId)}",
            "csrfToken": "${RES_BODY(data.csrfToken)}",
            "sessionCookie": "${RES_COOKIE(session_id)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.10 POST /api/v1/orders/pending ---
    sources.append(HttpSourceConfig(
        sourceCode="httpCreatePendingOrder",
        sourceName="创建待支付订单",
        tags=["订单", "创建", "待支付"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            CapabilitySideEffect(effectType="CREATE_ORDER", target="trade_order", description="创建待支付订单记录"),
        ],
        agentDescription="创建待支付状态的订单，支付状态为 PENDING，适用于测试支付前订单状态",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/orders/pending",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "buyer_id": "${input.buyer_id}",
            "amount": "${input.amount}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "order_id": "${RES_BODY(data.order_id)}",
            "pay_status": "${RES_BODY(data.pay_status)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.11 POST /api/v1/orders/with-items ---
    sources.append(HttpSourceConfig(
        sourceCode="httpCreateOrderWithItems",
        sourceName="创建带商品订单",
        tags=["订单", "商品", "创建", "库存"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            CapabilitySideEffect(effectType="CREATE_ORDER", target="trade_order", description="创建订单记录"),
            CapabilitySideEffect(effectType="MODIFY_INVENTORY", target="inventory", description="锁定商品库存"),
        ],
        agentDescription="创建包含商品明细的订单，同时锁定库存数量，适用于测试完整下单流程",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/orders/with-items",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "buyer_id": "${input.buyer_id}",
            "product_id": "${input.product_id}",
            "quantity": "${input.quantity}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "order_id": "${RES_BODY(data.order_id)}",
            "inventory_locked": "${RES_BODY(data.inventory_locked)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.12 POST /api/v1/payments ---
    sources.append(HttpSourceConfig(
        sourceCode="httpCreatePayment",
        sourceName="发起支付",
        tags=["支付", "付款", "扣款"],
        capabilityType=CapabilityType.UPDATE,
        businessDomain="支付",
        sideEffects=[
            CapabilitySideEffect(effectType="MODIFY_PAYMENT", target="payment_record", description="创建支付记录"),
            CapabilitySideEffect(effectType="MODIFY_ACCOUNT", target="user_account", description="扣减账户余额"),
        ],
        agentDescription="对指定订单发起支付操作，从用户账户扣款，涉及资金变动需确认",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/payments",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "order_id": "${input.order_id}",
            "payment_method": "${input.payment_method}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "payment_id": "${RES_BODY(data.payment_id)}",
            "status": "${RES_BODY(data.status)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.13 GET /api/v1/payments/{order_id}/status ---
    sources.append(HttpSourceConfig(
        sourceCode="httpQueryPaymentStatus",
        sourceName="查询支付状态",
        tags=["支付", "查询", "状态"],
        capabilityType=CapabilityType.QUERY,
        businessDomain="支付",
        sideEffects=[],
        agentDescription="查询订单当前的支付状态，纯查询操作无副作用",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/payments/${input.order_id}/status",
        method=HttpMethod.GET,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping={
            "headers": {"Accept": "application/json"},
        },
        responseHandling=_success_response_handling(),
        outputMapping={
            "pay_status": "${RES_BODY(data.pay_status)}",
            "paid_at": "${RES_BODY(data.paid_at)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.14 POST /api/v1/inventory/lock ---
    sources.append(HttpSourceConfig(
        sourceCode="httpLockInventory",
        sourceName="锁定库存",
        tags=["库存", "锁定", "预占"],
        capabilityType=CapabilityType.UPDATE,
        businessDomain="库存",
        sideEffects=[
            CapabilitySideEffect(effectType="MODIFY_INVENTORY", target="inventory", description="锁定商品库存数量"),
        ],
        agentDescription="为订单锁定商品库存，防止超卖",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/inventory/lock",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "product_id": "${input.product_id}",
            "quantity": "${input.quantity}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "lock_id": "${RES_BODY(data.lock_id)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.15 POST /api/v1/orders/{order_id}/refund ---
    sources.append(HttpSourceConfig(
        sourceCode="httpRefundOrder",
        sourceName="订单退款",
        tags=["退款", "退单", "订单"],
        capabilityType=CapabilityType.UPDATE,
        businessDomain="交易",
        sideEffects=[
            CapabilitySideEffect(effectType="MODIFY_ORDER", target="trade_order", description="更新订单状态为已退款"),
            CapabilitySideEffect(effectType="MODIFY_PAYMENT", target="payment_record", description="创建退款记录"),
        ],
        agentDescription="处理订单退款申请，退回支付金额到用户账户，涉及资金操作",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/orders/${input.order_id}/refund",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "refund_amount": "${input.refund_amount}",
            "refund_reason": "${input.refund_reason}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "refund_id": "${RES_BODY(data.refund_id)}",
            "status": "${RES_BODY(data.status)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    # --- 5.16 POST /api/v1/orders/fail ---
    sources.append(HttpSourceConfig(
        sourceCode="httpIntentionalFailOrder",
        sourceName="创建订单（故意失败测试）",
        tags=["订单", "创建", "测试", "黑名单"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            CapabilitySideEffect(effectType="CREATE_ORDER", target="trade_order", description="创建订单记录"),
        ],
        agentDescription="测试用场景，当 buyer_id 为 FAIL_USER 时故意失败，用于验证错误处理和黑名单机制",
        sysCode=HTTP_SYS_CODE,
        path="/api/v1/orders/fail",
        method=HttpMethod.POST,
        timeoutConfig=HttpTimeoutConfig(),
        requestMapping=_json_request_mapping({
            "buyer_id": "${input.buyer_id}",
        }),
        responseHandling=_success_response_handling(),
        outputMapping={
            "order_id": "${RES_BODY(data.order_id)}",
        },
        status=ConfigStatus.ENABLED,
    ))

    return sources


# ============================================================
# 6. SQL 配置
# ============================================================


def build_sql_sources() -> list[SqlSourceConfig]:
    """构建与 datagen_mock_sqlite.py 的 SQLite 表对应的 SQL 配置。"""
    return [
        # --- 6.1 查询会员账户状态 ---
        SqlSourceConfig(
            sourceCode="mockQueryMemberStatus",
            sourceName="查询会员账户状态",
            tags=["会员", "查询", "账户"],
            capabilityType=CapabilityType.QUERY,
            businessDomain="用户",
            sideEffects=[],
            agentDescription="按用户 ID 查询会员账户信息，包含手机号、会员等级、账户状态和积分",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.SELECT,
            sqlText=(
                "SELECT user_id, mobile, member_level, account_status, points "
                "FROM member_account WHERE user_id = :userId"
            ),
            normalizedSql=(
                "SELECT user_id, mobile, member_level, account_status, points "
                "FROM member_account WHERE user_id = :userId"
            ),
            parameters=[
                SqlSourceParameter(
                    name="userId",
                    type=InputFieldType.STRING,
                    required=True,
                    defaultValue="U10001",
                    description="会员用户 ID",
                ),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=None),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.2 按 SKU 查询库存 ---
        SqlSourceConfig(
            sourceCode="mockQueryInventoryBySku",
            sourceName="按 SKU 查询库存",
            tags=["库存", "查询", "SKU", "商品"],
            capabilityType=CapabilityType.QUERY,
            businessDomain="库存",
            sideEffects=[],
            agentDescription="按商品 SKU 编码查询库存信息，包含商品名称、价格、库存数量和锁定数量",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.SELECT,
            sqlText=(
                "SELECT p.sku_id, p.product_name, p.sale_price, i.stock_num, "
                "i.locked_num, i.status FROM product_sku p "
                "JOIN inventory i ON p.sku_id = i.sku_id "
                "WHERE p.sku_id = :skuId"
            ),
            normalizedSql=(
                "SELECT p.sku_id, p.product_name, p.sale_price, i.stock_num, "
                "i.locked_num, i.status FROM product_sku p "
                "JOIN inventory i ON p.sku_id = i.sku_id "
                "WHERE p.sku_id = :skuId"
            ),
            parameters=[
                SqlSourceParameter(
                    name="skuId",
                    type=InputFieldType.STRING,
                    required=True,
                    defaultValue="SKU10001",
                    description="商品 SKU 编码",
                ),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=None),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.3 创建交易订单 ---
        SqlSourceConfig(
            sourceCode="mockCreateOrder",
            sourceName="创建交易订单",
            tags=["订单", "创建", "交易"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="交易",
            sideEffects=[
                CapabilitySideEffect(effectType="CREATE_ORDER", target="trade_order", description="创建交易订单记录"),
            ],
            agentDescription="在交易订单表中创建新订单，状态初始为 CREATED",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.INSERT,
            sqlText=(
                "INSERT INTO trade_order(order_no, user_id, sku_id, quantity, "
                "order_amount, order_status, created_at) VALUES "
                "(:orderNo, :userId, :skuId, :quantity, :orderAmount, 'CREATED', CURRENT_TIMESTAMP)"
            ),
            normalizedSql=(
                "INSERT INTO trade_order(order_no, user_id, sku_id, quantity, "
                "order_amount, order_status, created_at) VALUES "
                "(:orderNo, :userId, :skuId, :quantity, :orderAmount, 'CREATED', CURRENT_TIMESTAMP)"
            ),
            parameters=[
                SqlSourceParameter(name="orderNo", type=InputFieldType.STRING, required=True, defaultValue="T202606069999", description="订单号"),
                SqlSourceParameter(name="userId", type=InputFieldType.STRING, required=True, defaultValue="U10001", description="下单用户 ID"),
                SqlSourceParameter(name="skuId", type=InputFieldType.STRING, required=True, defaultValue="SKU10001", description="商品 SKU 编码"),
                SqlSourceParameter(name="quantity", type=InputFieldType.NUMBER, required=True, defaultValue=1, description="购买数量"),
                SqlSourceParameter(name="orderAmount", type=InputFieldType.NUMBER, required=True, defaultValue=299.0, description="订单金额"),
            ],
            safety=SqlSourceSafety(requireWhere=False, maxAffectedRows=1),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.4 锁定库存 ---
        SqlSourceConfig(
            sourceCode="mockLockInventory",
            sourceName="锁定库存",
            tags=["库存", "锁定", "更新"],
            capabilityType=CapabilityType.UPDATE,
            businessDomain="库存",
            sideEffects=[
                CapabilitySideEffect(effectType="MODIFY_INVENTORY", target="inventory", description="减少可用库存，增加锁定数量"),
            ],
            agentDescription="按 SKU 锁定指定数量的库存，减少可用库存并增加锁定数量",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.UPDATE,
            sqlText=(
                "UPDATE inventory SET stock_num = stock_num - :quantity, "
                "locked_num = locked_num + :quantity, updated_at = CURRENT_TIMESTAMP "
                "WHERE sku_id = :skuId AND stock_num >= :quantity"
            ),
            normalizedSql=(
                "UPDATE inventory SET stock_num = stock_num - :quantity, "
                "locked_num = locked_num + :quantity, updated_at = CURRENT_TIMESTAMP "
                "WHERE sku_id = :skuId AND stock_num >= :quantity"
            ),
            parameters=[
                SqlSourceParameter(name="skuId", type=InputFieldType.STRING, required=True, defaultValue="SKU10001", description="商品 SKU 编码"),
                SqlSourceParameter(name="quantity", type=InputFieldType.NUMBER, required=True, defaultValue=1, description="锁定数量"),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=1),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.5 删除未支付订单 ---
        SqlSourceConfig(
            sourceCode="mockDeletePendingOrder",
            sourceName="删除未支付订单",
            tags=["订单", "删除", "清理"],
            capabilityType=CapabilityType.UPDATE,
            businessDomain="交易",
            sideEffects=[
                CapabilitySideEffect(effectType="DELETE_ORDER", target="trade_order", description="删除未支付的订单记录"),
            ],
            agentDescription="删除状态为 CREATED（未支付）的订单记录",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.DELETE,
            sqlText="DELETE FROM trade_order WHERE order_no = :orderNo AND order_status = 'CREATED'",
            normalizedSql="DELETE FROM trade_order WHERE order_no = :orderNo AND order_status = 'CREATED'",
            parameters=[
                SqlSourceParameter(name="orderNo", type=InputFieldType.STRING, required=True, defaultValue="T202606060002", description="待删除订单号"),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=1),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.6 写入订单日志 ---
        SqlSourceConfig(
            sourceCode="mockInsertOrderLog",
            sourceName="写入订单日志",
            tags=["订单", "日志", "审计"],
            capabilityType=CapabilityType.CREATE,
            businessDomain="交易",
            sideEffects=[
                CapabilitySideEffect(effectType="WRITE_LOG", target="order_log", description="写入订单操作日志"),
            ],
            agentDescription="向订单日志表写入操作记录，记录订单号、用户、操作类型和备注",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.INSERT,
            sqlText=(
                "INSERT INTO order_log(order_no, user_id, action_type, remark, created_at) "
                "VALUES (:orderNo, :userId, :actionType, :remark, CURRENT_TIMESTAMP)"
            ),
            normalizedSql=(
                "INSERT INTO order_log(order_no, user_id, action_type, remark, created_at) "
                "VALUES (:orderNo, :userId, :actionType, :remark, CURRENT_TIMESTAMP)"
            ),
            parameters=[
                SqlSourceParameter(name="orderNo", type=InputFieldType.STRING, required=True, defaultValue="T202606060001", description="订单号"),
                SqlSourceParameter(name="userId", type=InputFieldType.STRING, required=True, defaultValue="U10001", description="用户 ID"),
                SqlSourceParameter(name="actionType", type=InputFieldType.STRING, required=True, defaultValue="CREATE_ORDER", description="操作类型"),
                SqlSourceParameter(name="remark", type=InputFieldType.STRING, required=False, defaultValue="mock log", description="日志备注"),
            ],
            safety=SqlSourceSafety(requireWhere=False, maxAffectedRows=1),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.7 查询会员订单列表 ---
        SqlSourceConfig(
            sourceCode="mockQueryMemberOrders",
            sourceName="查询会员订单列表",
            tags=["订单", "查询", "会员", "列表"],
            capabilityType=CapabilityType.QUERY,
            businessDomain="交易",
            sideEffects=[],
            agentDescription="按用户 ID 查询其所有订单，包含订单号、商品 SKU、数量、金额和状态",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.SELECT,
            sqlText=(
                "SELECT order_no, user_id, sku_id, quantity, order_amount, order_status, created_at, paid_at "
                "FROM trade_order WHERE user_id = :userId"
            ),
            normalizedSql=(
                "SELECT order_no, user_id, sku_id, quantity, order_amount, order_status, created_at, paid_at "
                "FROM trade_order WHERE user_id = :userId"
            ),
            parameters=[
                SqlSourceParameter(name="userId", type=InputFieldType.STRING, required=True, defaultValue="U10001", description="用户 ID"),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=None),
            status=ConfigStatus.ENABLED,
        ),

        # --- 6.8 查询所有商品 ---
        SqlSourceConfig(
            sourceCode="mockQueryAllProducts",
            sourceName="查询所有商品",
            tags=["商品", "查询", "列表", "SKU"],
            capabilityType=CapabilityType.QUERY,
            businessDomain="商品",
            sideEffects=[],
            agentDescription="查询所有商品信息，包含 SKU、名称、分类、价格和上架状态",
            sysCode=SQL_SYS_CODE,
            datasourceCode="mockTradeSqlite",
            operation=SqlOperation.SELECT,
            sqlText="SELECT sku_id, product_name, category, sale_price, status FROM product_sku",
            normalizedSql="SELECT sku_id, product_name, category, sale_price, status FROM product_sku",
            parameters=[],
            safety=SqlSourceSafety(requireWhere=False, maxAffectedRows=None),
            status=ConfigStatus.ENABLED,
        ),
    ]


# ============================================================
# 7. 标识引用配置
# ============================================================


def build_identifier_references() -> list[IdentifierReferenceConfig]:
    return [
        IdentifierReferenceConfig(
            refCode="TIME",
            refName="时间偏移",
            refType="TIME",
            syntax="${TIME(format,offset)}",
            description="在请求或断言中引用当前时间，支持自定义格式和偏移量。例如生成当天日期、指定偏移的天数。",
            usageScope=["发送前", "报文节点", "预期结果"],
            parameters=[
                IdentifierReferenceParameter(name="format", description="时间格式，例如 yyyy-MM-dd、yyyyMMddHHmmss", required=True, defaultValue="yyyy-MM-dd"),
                IdentifierReferenceParameter(name="offset", description="偏移量，支持 +1d、-2h、+30m 等格式", required=False, defaultValue="0"),
            ],
            examples=[
                IdentifierReferenceExample(expression="${TIME(yyyy-MM-dd,0)}", description="当天日期，例如 2026-06-15"),
                IdentifierReferenceExample(expression="${TIME(yyyyMMddHHmmss,+1d)}", description="明天完整时间戳，例如 20260616120000"),
                IdentifierReferenceExample(expression="${TIME(yyyy-MM,-1M)}", description="上个月，例如 2026-05"),
            ],
            status=ConfigStatus.ENABLED,
            remark="最常用的标识引用，适合生成动态时间参数。",
        ),
        IdentifierReferenceConfig(
            refCode="MATCHER",
            refName="正则匹配",
            refType="MATCHER",
            syntax="${MATCHER(pattern)}",
            description="在预期结果中使用正则表达式进行模糊匹配断言，适用于响应字段值不确定但符合特定格式的场景。",
            usageScope=["预期结果", "发送后处理"],
            parameters=[
                IdentifierReferenceParameter(name="pattern", description="正则表达式模式", required=True, defaultValue=".*"),
            ],
            examples=[
                IdentifierReferenceExample(expression="${MATCHER(\\d{11})}", description="匹配 11 位数字（手机号）"),
                IdentifierReferenceExample(expression="${MATCHER([A-Z]{2}\\d{8})}", description="匹配特定格式编码"),
                IdentifierReferenceExample(expression="${MATCHER(^U\\d{5}$)}", description="匹配以 U 开头后跟 5 位数字的用户 ID"),
            ],
            status=ConfigStatus.ENABLED,
            remark="用于断言阶段的模糊匹配，不用于请求构造。",
        ),
        IdentifierReferenceConfig(
            refCode="TPN",
            refName="事务处理号",
            refType="TPN",
            syntax="${TPN(prefix)}",
            description="生成全局唯一的事务处理号，用于串联多步骤操作或作为幂等键。每次执行生成新值。",
            usageScope=["发送前", "报文节点"],
            parameters=[
                IdentifierReferenceParameter(name="prefix", description="前缀字符串", required=False, defaultValue="TPN"),
            ],
            examples=[
                IdentifierReferenceExample(expression="${TPN(ORD)}", description="生成 ORD 前缀的事务号，例如 ORD20260615120000001"),
                IdentifierReferenceExample(expression="${TPN()}", description="默认前缀的事务号"),
            ],
            status=ConfigStatus.ENABLED,
            remark="每次执行生成唯一值，适合作为请求流水号或幂等键。",
        ),
        IdentifierReferenceConfig(
            refCode="LOGIN",
            refName="登录变量",
            refType="LOGIN",
            syntax="${LOGIN(varName)}",
            description="引用登录阶段获取的会话变量，例如 Token、Session ID、Cookie 等。需要先通过登录接口获取。",
            usageScope=["发送前", "报文节点"],
            parameters=[
                IdentifierReferenceParameter(name="varName", description="登录阶段定义的变量名", required=True, defaultValue="access_token"),
            ],
            examples=[
                IdentifierReferenceExample(expression="${LOGIN(access_token)}", description="引用登录获取的访问令牌"),
                IdentifierReferenceExample(expression="${LOGIN(session_id)}", description="引用登录获取的会话 ID"),
                IdentifierReferenceExample(expression="${LOGIN(csrf_token)}", description="引用登录获取的 CSRF Token"),
            ],
            status=ConfigStatus.ENABLED,
            remark="依赖前置登录步骤，变量在登录响应中通过 outputMapping 提取。",
        ),
        IdentifierReferenceConfig(
            refCode="BASE64",
            refName="Base64 编码",
            refType="BASE64",
            syntax="${BASE64(content)}",
            description="对指定内容进行 Base64 编码，常用于 Basic Auth 凭证构造或报文编码。",
            usageScope=["发送前", "报文节点"],
            parameters=[
                IdentifierReferenceParameter(name="content", description="待编码的原始内容", required=True, defaultValue=""),
            ],
            examples=[
                IdentifierReferenceExample(expression="${BASE64(client_id:client_secret)}", description="Base64 编码客户端凭证"),
                IdentifierReferenceExample(expression="${BASE64(user:pass)}", description="Base64 编码用户名密码用于 Basic Auth"),
            ],
            status=ConfigStatus.ENABLED,
            remark="常用于构造 Authorization: Basic xxx 请求头。",
        ),
    ]


# ============================================================
# 8. Mock SQLite 业务数据库
# ============================================================


def create_mock_sqlite_db(output_dir: Path) -> Path:
    """创建 Mock SQLite 业务数据库，包含会员、商品、库存、订单等业务表。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "gdp_mock_trade.sqlite"

    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # 建表
        conn.executescript("""
            CREATE TABLE member_account (
              user_id TEXT PRIMARY KEY,
              mobile TEXT NOT NULL,
              member_level TEXT NOT NULL,
              account_status TEXT NOT NULL,
              points INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL
            );

            CREATE TABLE product_sku (
              sku_id TEXT PRIMARY KEY,
              product_name TEXT NOT NULL,
              category TEXT NOT NULL,
              sale_price REAL NOT NULL,
              status TEXT NOT NULL
            );

            CREATE TABLE inventory (
              sku_id TEXT PRIMARY KEY,
              stock_num INTEGER NOT NULL,
              locked_num INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY (sku_id) REFERENCES product_sku(sku_id)
            );

            CREATE TABLE trade_order (
              order_no TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              sku_id TEXT NOT NULL,
              quantity INTEGER NOT NULL,
              order_amount REAL NOT NULL,
              order_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              paid_at TEXT,
              FOREIGN KEY (user_id) REFERENCES member_account(user_id),
              FOREIGN KEY (sku_id) REFERENCES product_sku(sku_id)
            );

            CREATE TABLE order_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              order_no TEXT NOT NULL,
              user_id TEXT NOT NULL,
              action_type TEXT NOT NULL,
              remark TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 会员账户
        conn.executemany(
            "INSERT INTO member_account (user_id, mobile, member_level, account_status, points, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("U10001", "13800000001", "VIP", "ACTIVE", 6200, "2026-01-10 09:10:00"),
                ("U10002", "13800000002", "NORMAL", "ACTIVE", 800, "2026-02-14 10:20:00"),
                ("U10003", "13800000003", "NORMAL", "FROZEN", 120, "2026-03-02 16:45:00"),
                ("U10004", "13800000004", "SVIP", "ACTIVE", 18800, "2026-04-18 08:30:00"),
            ],
        )

        # 商品 SKU
        conn.executemany(
            "INSERT INTO product_sku (sku_id, product_name, category, sale_price, status) VALUES (?, ?, ?, ?, ?)",
            [
                ("SKU10001", "机械键盘 K87", "electronics", 299.00, "ON_SALE"),
                ("SKU10002", "无线鼠标 M2", "electronics", 129.00, "ON_SALE"),
                ("SKU10003", "保温杯 500ml", "daily", 59.90, "OFF_SHELF"),
                ("SKU10004", "人体工学椅", "office", 899.00, "ON_SALE"),
            ],
        )

        # 库存
        conn.executemany(
            "INSERT INTO inventory (sku_id, stock_num, locked_num, status, updated_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("SKU10001", 120, 4, "AVAILABLE", "2026-06-06 09:00:00"),
                ("SKU10002", 35, 2, "AVAILABLE", "2026-06-06 09:10:00"),
                ("SKU10003", 0, 0, "SOLD_OUT", "2026-06-06 09:20:00"),
                ("SKU10004", 8, 1, "LOW_STOCK", "2026-06-06 09:30:00"),
            ],
        )

        # 交易订单
        conn.executemany(
            "INSERT INTO trade_order (order_no, user_id, sku_id, quantity, order_amount, order_status, created_at, paid_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("T202606060001", "U10001", "SKU10001", 1, 299.00, "PAID", "2026-06-06 10:00:00", "2026-06-06 10:01:20"),
                ("T202606060002", "U10002", "SKU10002", 2, 258.00, "CREATED", "2026-06-06 10:15:00", None),
                ("T202606060003", "U10004", "SKU10004", 1, 899.00, "PAID", "2026-06-06 10:30:00", "2026-06-06 10:31:10"),
            ],
        )

        # 订单日志
        conn.executemany(
            "INSERT INTO order_log (order_no, user_id, action_type, remark, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("T202606060001", "U10001", "CREATE_ORDER", "创建订单", "2026-06-06 10:00:00"),
                ("T202606060001", "U10001", "PAY_ORDER", "支付完成", "2026-06-06 10:01:20"),
                ("T202606060002", "U10002", "CREATE_ORDER", "创建订单待支付", "2026-06-06 10:15:00"),
            ],
        )

        conn.commit()

    print(f"  Mock SQLite 数据库: {db_path}")
    return db_path


# ============================================================
# 写入逻辑
# ============================================================


async def seed_base_config(
    base_service: BaseConfigService,
    mock_db_path: Path,
) -> None:
    """写入系统、环境、服务端点、数据源。"""
    print("\n--- 写入系统配置 ---")
    for sys_config in build_systems():
        await base_service.upsert_system(sys_config, operator=OPERATOR)
        print(f"  [OK] 系统: {sys_config.sysCode} ({sys_config.sysName})")

    print("\n--- 写入环境配置 ---")
    for env_config in build_environments():
        await base_service.upsert_environment(env_config, operator=OPERATOR)
        print(f"  [OK] 环境: {env_config.envCode} ({env_config.envName})")

    print("\n--- 写入服务端点 ---")
    for ep in build_service_endpoints():
        existing = await base_service.list_service_endpoints(env_code=ep.envCode, sys_code=ep.sysCode)
        if existing:
            await base_service.update_service_endpoint(existing[0].id, ep, operator=OPERATOR)
            print(f"  [OK] 更新端点: {ep.envCode}/{ep.sysCode} -> {ep.baseUrl}")
        else:
            await base_service.create_service_endpoint(ep, operator=OPERATOR)
            print(f"  [OK] 创建端点: {ep.envCode}/{ep.sysCode} -> {ep.baseUrl}")

    print("\n--- 写入数据源 ---")
    for ds in build_datasources(mock_db_path):
        existing = await base_service.list_datasources(env_code=ds.envCode, sys_code=ds.sysCode)
        match = next((item for item in existing if item.datasourceCode == ds.datasourceCode), None)
        if match:
            await base_service.update_datasource(match.id, ds, operator=OPERATOR)
            print(f"  [OK] 更新数据源: {ds.envCode}/{ds.sysCode}/{ds.datasourceCode}")
        else:
            await base_service.create_datasource(ds, operator=OPERATOR)
            print(f"  [OK] 创建数据源: {ds.envCode}/{ds.sysCode}/{ds.datasourceCode}")


async def seed_identifier_references(session_factory: Any) -> None:
    """直接写入标识引用配置（BaseConfigService 暂无对应方法，直接操作 ORM）。"""
    from app.gdp.datagen.config.base.repository import DataFactoryIdentifierReferenceRow
    from sqlalchemy import select

    print("\n--- 写入标识引用配置 ---")
    for ref in build_identifier_references():
        async with session_factory() as session:
            stmt = select(DataFactoryIdentifierReferenceRow).where(
                DataFactoryIdentifierReferenceRow.ref_code == ref.refCode,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            from datetime import UTC, datetime
            import uuid

            now = datetime.now(UTC)
            if existing:
                existing.ref_name = ref.refName
                existing.ref_type = ref.refType.value
                existing.syntax = ref.syntax
                existing.description = ref.description
                existing.usage_scope_json = _dumps(ref.usageScope)
                existing.parameters_json = _dumps([p.model_dump() for p in ref.parameters])
                existing.examples_json = _dumps([e.model_dump() for e in ref.examples])
                existing.status = ref.status.value
                existing.remark = ref.remark
                existing.updated_at = now
                action = "更新"
            else:
                session.add(DataFactoryIdentifierReferenceRow(
                    id=str(uuid.uuid4()),
                    ref_code=ref.refCode,
                    ref_name=ref.refName,
                    ref_type=ref.refType.value,
                    syntax=ref.syntax,
                    description=ref.description,
                    usage_scope_json=_dumps(ref.usageScope),
                    parameters_json=_dumps([p.model_dump() for p in ref.parameters]),
                    examples_json=_dumps([e.model_dump() for e in ref.examples]),
                    status=ref.status.value,
                    remark=ref.remark,
                    created_at=now,
                    updated_at=now,
                ))
                action = "创建"
            await session.commit()
            print(f"  [OK] {action}标识引用: {ref.refCode} ({ref.refName})")


async def seed_http_sources(http_service: HttpSourceService) -> None:
    """写入 HTTP 接口配置。"""
    print("\n--- 写入 HTTP 接口配置 ---")
    for config in build_http_sources():
        await http_service.upsert_http_source(config, operator=OPERATOR)
        print(f"  [OK] HTTP Source: {config.sourceCode} ({config.sourceName}) [{config.method.value} {config.path}]")


async def seed_sql_sources(sql_service: SqlSourceService) -> None:
    """写入 SQL 配置。"""
    print("\n--- 写入 SQL 配置 ---")
    for config in build_sql_sources():
        await sql_service.upsert_sql_source(config, operator=OPERATOR)
        print(f"  [OK] SQL Source: {config.sourceCode} ({config.sourceName}) [{config.operation.value}]")


async def run_seed(
    *,
    dry_run: bool = False,
    http_only: bool = False,
    sql_only: bool = False,
) -> None:
    """执行种子数据写入。"""
    mode_parts = []
    if dry_run:
        mode_parts.append("预览（不写库）")
    if http_only:
        mode_parts.append("仅 HTTP")
    if sql_only:
        mode_parts.append("仅 SQL")
    mode = "、".join(mode_parts) if mode_parts else "全量写入"

    print("=" * 60)
    print("GDP 造数系统基础模拟数据种子")
    print(f"模式: {mode}")
    print("=" * 60)

    # 创建 Mock SQLite 数据库（不论是否 dry-run，都展示路径信息）
    mock_db_dir = DEFAULT_MOCK_DB_DIR
    mock_db_path = mock_db_dir / "gdp_mock_trade.sqlite"

    if not dry_run and not http_only:
        print("\n--- 创建 Mock SQLite 业务数据库 ---")
        mock_db_path = create_mock_sqlite_db(mock_db_dir)

    if dry_run:
        print(f"\n[DRY-RUN] Mock SQLite 数据库路径: {mock_db_path}")
        print(f"[DRY-RUN] 系统: {[s.sysCode for s in build_systems()]}")
        print(f"[DRY-RUN] 环境: {[e.envCode for e in build_environments()]}")
        print(f"[DRY-RUN] 服务端点: {len(build_service_endpoints())} 个")
        print(f"[DRY-RUN] 数据源: {len(build_datasources(mock_db_path))} 个")
        if not sql_only:
            print(f"[DRY-RUN] HTTP Sources: {len(build_http_sources())} 个")
        if not http_only:
            print(f"[DRY-RUN] SQL Sources: {len(build_sql_sources())} 个")
            print(f"[DRY-RUN] 标识引用: {len(build_identifier_references())} 个")
        return

    # 初始化数据库引擎
    app_config = get_app_config()
    await init_engine_from_config(app_config.database)
    try:
        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeError("数据库未初始化，无法写入种子数据")

        base_repo = BaseConfigRepository(session_factory)
        base_service = BaseConfigService(base_repo)
        http_service = HttpSourceService(HttpSourceRepository(session_factory), base_repo)
        sql_service = SqlSourceService(SqlSourceRepository(session_factory), base_repo)

        # 基础配置（系统、环境、端点、数据源）— 两种模式都需要
        if not http_only and not sql_only:
            await seed_base_config(base_service, mock_db_path)

        # 如果只写 HTTP 或只写 SQL，也需要基础配置
        if http_only or sql_only:
            await seed_base_config(base_service, mock_db_path)

        # HTTP 接口配置
        if not sql_only:
            await seed_http_sources(http_service)

        # SQL 配置
        if not http_only:
            await seed_sql_sources(sql_service)

        # 标识引用
        if not http_only and not sql_only:
            await seed_identifier_references(session_factory)

        print("\n" + "=" * 60)
        print("[OK] 种子数据写入完成！")
        print("=" * 60)
        print("\n后续步骤:")
        print(f"  1. 启动 Mock HTTP 服务: cd backend && python scripts/datagen_http_mock_server.py")
        print(f"  2. 前端查看配置: http://localhost:2026/gdp/datagen")
        print(f"  3. Mock SQLite DB: {mock_db_path}")
        print(f"  4. 如需重跑种子: cd backend && PYTHONPATH=. uv run python scripts/seed_gdp_mock_data.py")

    finally:
        await close_engine()


# ============================================================
# 入口
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="GDP 造数系统基础模拟数据种子")
    parser.add_argument("--dry-run", action="store_true", help="预览不写库")
    parser.add_argument("--http-only", action="store_true", help="只写 HTTP 相关配置")
    parser.add_argument("--sql-only", action="store_true", help="只写 SQL 相关配置")
    args = parser.parse_args()

    try:
        asyncio.run(run_seed(
            dry_run=args.dry_run,
            http_only=args.http_only,
            sql_only=args.sql_only,
        ))
    finally:
        asyncio.run(close_engine())


if __name__ == "__main__":
    main()
