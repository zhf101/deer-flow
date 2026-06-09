"""向本地数据库写入 datagen 新步骤模型演示数据。"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    EnvironmentConfig,
    ServiceEndpointConfig,
    SysConfig,
)
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.base.service import BaseConfigService
from app.gdp.datagen.config.common.models import (
    ConfigStatus,
    HttpMethod,
    InputFieldType,
    SceneStatus,
    SqlOperation,
    SqlSourceSafety,
)
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.models import (
    BatchConfig,
    HttpStepDefinition,
    Position,
    SceneDefinition,
    SqlStepDefinition,
)
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQL_CONFIG = ROOT / ".deer-flow/datagen/mock/gdp_mock_sql_config.json"
DEFAULT_MOCK_SQLITE = ROOT / ".deer-flow/datagen/mock/gdp_mock_trade.sqlite"
DEFAULT_HTTP_BASE_URL = "http://127.0.0.1:18080"
OPERATOR = "datagen-new-model-seed"
HTTP_SYS_CODE = "SYS_HTTP_TEST"
TRADE_SYS_CODE = "mockTrade"
TRADE_DATASOURCE_CODE = "mockTradeSqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="写入 datagen 新步骤模型本地联调数据")
    parser.add_argument("--mock-base-url", default=DEFAULT_HTTP_BASE_URL, help="本地 HTTP mock server Base URL")
    parser.add_argument("--sql-config", type=Path, default=DEFAULT_SQL_CONFIG, help="mock SQL 配置 JSON")
    parser.add_argument("--mock-sqlite", type=Path, default=DEFAULT_MOCK_SQLITE, help="mock SQLite 数据库文件")
    parser.add_argument("--regenerate-mock-sqlite", action="store_true", help="重新生成 mock SQLite 业务数据")
    args = parser.parse_args()
    asyncio.run(seed(args))


async def seed(args: argparse.Namespace) -> None:
    sql_config_path = args.sql_config.resolve()
    mock_sqlite_path = args.mock_sqlite.resolve()
    ensure_mock_sqlite(mock_sqlite_path, regenerate=args.regenerate_mock_sqlite)

    app_config = get_app_config()
    await init_engine_from_config(app_config.database)
    try:
        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeError("当前数据库 backend=memory，无法写入本地持久化测试数据。")

        base_repo = BaseConfigRepository(session_factory)
        base_service = BaseConfigService(base_repo)
        http_service = HttpSourceService(HttpSourceRepository(session_factory), base_repo)
        sql_service = SqlSourceService(SqlSourceRepository(session_factory), base_repo)
        scene_service = SceneService(SceneRepository(session_factory))

        sql_payload = load_sql_payload(sql_config_path, mock_sqlite_path)
        await seed_base_config(base_service, sql_payload, mock_base_url=args.mock_base_url)
        await seed_sql_sources(sql_service, sql_payload)
        await seed_http_sources(http_service)
        await upsert_scene(scene_service, build_integration_draft_scene())
        await upsert_and_publish_scene(scene_service, build_sql_runnable_scene())
        await upsert_and_publish_scene(scene_service, build_full_stack_complex_scene())

        print("写入完成：")
        print(f"- HTTP mock 系统: {HTTP_SYS_CODE} -> {args.mock_base_url}")
        print(f"- SQLite mock 系统: {TRADE_SYS_CODE}/{TRADE_DATASOURCE_CODE} -> {mock_sqlite_path}")
        print("- HTTP 源: mockOAuthToken, mockGetAccountDetail, mockCreateUser, mockQueryDictionary, mockGetUserListWithHeaders, mockSessionLoginCookie, mockSoapCreateOrderXml, mockSendTextMessage, mockUploadFileFormData")
        print(
            "- SQL 源: mockQueryMemberStatus, mockQueryInventoryBySku, mockCreateOrder, "
            "mockLockInventory, mockDeletePendingOrder, mockInsertOrderLog, "
            "mockQueryOrderAggregateComplex, mockQueryInventoryRiskComplex, "
            "mockMyBatisDynamicOrderQuery, mockUpdateInventoryByComplexCondition, mockDeleteOldSeedLogs"
        )
        print("- 草稿场景: mock_http_sqlite_integration")
        print("- 已发布 SQL 场景: mock_sqlite_runnable_order_log")
        print("- 已发布复杂场景: mock_full_stack_http_sql_complex")
    finally:
        await close_engine()


def ensure_mock_sqlite(mock_sqlite_path: Path, *, regenerate: bool) -> None:
    if mock_sqlite_path.exists() and not regenerate:
        return
    from scripts.datagen_mock_sqlite import create_sqlite_database

    mock_sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    create_sqlite_database(mock_sqlite_path)


def load_sql_payload(config_path: Path, mock_sqlite_path: Path) -> dict[str, Any]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    database_name = str(mock_sqlite_path).replace("\\", "/")
    for datasource in payload.get("datasources", []):
        datasource["databaseName"] = database_name
    return payload


async def seed_base_config(
    base_service: BaseConfigService,
    payload: dict[str, Any],
    *,
    mock_base_url: str,
) -> None:
    await base_service.upsert_system(
        SysConfig(
            sysCode=HTTP_SYS_CODE,
            sysName="本地 HTTP Mock 系统",
            status=ConfigStatus.ENABLED,
            remark="本地 datagen HTTP mock server，默认监听 127.0.0.1:18080。",
        ),
        operator=OPERATOR,
    )

    for item in payload.get("systems", []):
        await base_service.upsert_system(SysConfig.model_validate(item), operator=OPERATOR)

    for item in payload.get("environments", []):
        await base_service.upsert_environment(EnvironmentConfig.model_validate(item), operator=OPERATOR)

    for env_code in ("dev", "test"):
        await upsert_service_endpoint(
            base_service,
            ServiceEndpointConfig(
                envCode=env_code,
                sysCode=HTTP_SYS_CODE,
                baseUrl=mock_base_url.rstrip("/"),
                status=ConfigStatus.ENABLED,
            ),
        )

    for item in payload.get("datasources", []):
        await upsert_datasource(base_service, DatasourceConfig.model_validate(item))


async def upsert_service_endpoint(
    base_service: BaseConfigService,
    config: ServiceEndpointConfig,
) -> None:
    existing = await base_service.list_service_endpoints(env_code=config.envCode, sys_code=config.sysCode)
    if existing:
        await base_service.update_service_endpoint(existing[0].id, config, operator=OPERATOR)
        return
    await base_service.create_service_endpoint(config, operator=OPERATOR)


async def upsert_datasource(
    base_service: BaseConfigService,
    config: DatasourceConfig,
) -> None:
    existing = await base_service.list_datasources(env_code=config.envCode, sys_code=config.sysCode)
    match = next((item for item in existing if item.datasourceCode == config.datasourceCode), None)
    if match is None:
        await base_service.create_datasource(config, operator=OPERATOR)
        return
    await base_service.update_datasource(match.id, config, operator=OPERATOR)


async def seed_sql_sources(sql_service: SqlSourceService, payload: dict[str, Any]) -> None:
    for item in payload.get("sqlSources", []):
        await sql_service.upsert_sql_source(SqlSourceConfig.model_validate(item), operator=OPERATOR)
    for config in build_extra_sql_sources():
        await sql_service.upsert_sql_source(config, operator=OPERATOR)


async def seed_http_sources(http_service: HttpSourceService) -> None:
    for config in build_http_sources():
        await http_service.upsert_http_source(config, operator=OPERATOR)


def build_extra_sql_sources() -> list[SqlSourceConfig]:
    return [
        SqlSourceConfig(
            sourceCode="mockQueryOrderAggregateComplex",
            sourceName="Mock 复杂聚合查询订单概览",
            sysCode=TRADE_SYS_CODE,
            datasourceCode=TRADE_DATASOURCE_CODE,
            operation=SqlOperation.SELECT,
            sqlText=(
                "WITH paid_orders AS ("
                "  SELECT user_id, COUNT(*) AS paid_count, SUM(order_amount) AS paid_amount "
                "  FROM trade_order WHERE order_status = :paidStatus GROUP BY user_id"
                ") "
                "SELECT m.user_id, m.member_level, m.account_status, "
                "       COALESCE(p.paid_count, 0) AS paid_count, "
                "       COALESCE(p.paid_amount, 0) AS paid_amount, "
                "       CASE WHEN COALESCE(p.paid_amount, 0) >= :vipAmount THEN 'HIGH_VALUE' ELSE 'NORMAL_VALUE' END AS value_tag "
                "FROM member_account m "
                "LEFT JOIN paid_orders p ON p.user_id = m.user_id "
                "WHERE m.user_id = :userId AND m.account_status IN ('ACTIVE', 'FROZEN')"
            ),
            parameters=[
                sql_parameter("paidStatus", InputFieldType.STRING, True, "PAID", "纳入聚合统计的订单状态"),
                sql_parameter("vipAmount", InputFieldType.NUMBER, True, 500, "高价值用户订单金额阈值"),
                sql_parameter("userId", InputFieldType.STRING, True, "U10001", "会员用户 ID"),
            ],
            safety=SqlSourceSafety(requireWhere=True),
            status=ConfigStatus.ENABLED,
        ),
        SqlSourceConfig(
            sourceCode="mockQueryInventoryRiskComplex",
            sourceName="Mock 复杂库存风险查询",
            sysCode=TRADE_SYS_CODE,
            datasourceCode=TRADE_DATASOURCE_CODE,
            operation=SqlOperation.SELECT,
            sqlText=(
                "SELECT p.sku_id, p.product_name, p.category, i.stock_num, i.locked_num, "
                "       (i.stock_num - i.locked_num) AS available_num, "
                "       CASE "
                "         WHEN p.status <> 'ON_SALE' THEN 'OFFLINE' "
                "         WHEN (i.stock_num - i.locked_num) <= :lowStockThreshold THEN 'RISK' "
                "         ELSE 'OK' "
                "       END AS inventory_risk, "
                "       EXISTS(SELECT 1 FROM trade_order o WHERE o.sku_id = p.sku_id AND o.order_status = :orderStatus) AS has_paid_order "
                "FROM product_sku p "
                "JOIN inventory i ON i.sku_id = p.sku_id "
                "WHERE p.category = :category AND p.status IN ('ON_SALE', 'OFF_SHELF') "
                "ORDER BY available_num ASC, p.sku_id ASC"
            ),
            parameters=[
                sql_parameter("lowStockThreshold", InputFieldType.NUMBER, True, 10, "低库存阈值"),
                sql_parameter("orderStatus", InputFieldType.STRING, True, "PAID", "判断历史订单的状态"),
                sql_parameter("category", InputFieldType.STRING, True, "electronics", "商品分类"),
            ],
            safety=SqlSourceSafety(requireWhere=True),
            status=ConfigStatus.ENABLED,
        ),
        SqlSourceConfig(
            sourceCode="mockMyBatisDynamicOrderQuery",
            sourceName="Mock MyBatis 动态订单查询",
            sysCode=TRADE_SYS_CODE,
            datasourceCode=TRADE_DATASOURCE_CODE,
            operation=SqlOperation.SELECT,
            sqlText=(
                "<select id=\"queryOrders\">\n"
                "  SELECT o.order_no, o.user_id, o.sku_id, o.quantity, o.order_amount, o.order_status, o.created_at,\n"
                "         m.member_level, p.product_name\n"
                "  FROM trade_order o\n"
                "  JOIN member_account m ON m.user_id = o.user_id\n"
                "  JOIN product_sku p ON p.sku_id = o.sku_id\n"
                "  <where>\n"
                "    <if test=\"userId != null\">AND o.user_id = #{userId}</if>\n"
                "    <if test=\"orderStatus != null\">AND o.order_status = #{orderStatus}</if>\n"
                "    <if test=\"minAmount != null\">AND o.order_amount &gt;= #{minAmount}</if>\n"
                "  </where>\n"
                "  ORDER BY o.created_at DESC\n"
                "</select>"
            ),
            parameters=[
                sql_parameter("userId", InputFieldType.STRING, True, "U10001", "订单所属用户 ID"),
                sql_parameter("orderStatus", InputFieldType.STRING, True, "PAID", "订单状态"),
                sql_parameter("minAmount", InputFieldType.NUMBER, False, 100, "最低订单金额"),
            ],
            safety=SqlSourceSafety(requireWhere=True),
            status=ConfigStatus.ENABLED,
        ),
        SqlSourceConfig(
            sourceCode="mockUpdateInventoryByComplexCondition",
            sourceName="Mock 复杂条件更新库存",
            sysCode=TRADE_SYS_CODE,
            datasourceCode=TRADE_DATASOURCE_CODE,
            operation=SqlOperation.UPDATE,
            sqlText=(
                "UPDATE inventory "
                "SET locked_num = locked_num + :quantity, updated_at = CURRENT_TIMESTAMP "
                "WHERE sku_id = :skuId "
                "  AND status IN ('AVAILABLE', 'LOW_STOCK') "
                "  AND stock_num - locked_num >= :quantity"
            ),
            parameters=[
                sql_parameter("quantity", InputFieldType.NUMBER, True, 1, "本次锁定数量"),
                sql_parameter("skuId", InputFieldType.STRING, True, "SKU10001", "商品 SKU 编码"),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=1),
            status=ConfigStatus.ENABLED,
        ),
        SqlSourceConfig(
            sourceCode="mockDeleteOldSeedLogs",
            sourceName="Mock 删除旧造数日志",
            sysCode=TRADE_SYS_CODE,
            datasourceCode=TRADE_DATASOURCE_CODE,
            operation=SqlOperation.DELETE,
            sqlText=(
                "DELETE FROM order_log "
                "WHERE action_type = :actionType "
                "  AND created_at < :beforeTime "
                "  AND remark LIKE :remarkPattern"
            ),
            parameters=[
                sql_parameter("actionType", InputFieldType.STRING, True, "SEED_SCENE_RUN", "待清理日志动作"),
                sql_parameter("beforeTime", InputFieldType.DATE, True, "2099-01-01 00:00:00", "清理截止时间"),
                sql_parameter("remarkPattern", InputFieldType.STRING, True, "%datagen%", "日志备注匹配模式"),
            ],
            safety=SqlSourceSafety(requireWhere=True, maxAffectedRows=20),
            status=ConfigStatus.ENABLED,
        ),
    ]


def build_http_sources() -> list[HttpSourceConfig]:
    return [
        HttpSourceConfig(
            sourceCode="mockOAuthToken",
            sourceName="Mock OAuth 获取 Token",
            sysCode=HTTP_SYS_CODE,
            path="/oauth/token",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                "authConfig": {"type": "basic", "username": "mock-client", "password": "mock-secret"},
                "bodyType": "x-www-form-urlencoded",
                "urlEncodedData": {
                    "grant_type": "password",
                    "username": "demo_user",
                    "password": "demo_password",
                    "scope": "account:user",
                },
            },
            responseHandling=success_response_handling("RES_BODY(access_token)", "NOT_EMPTY", ""),
            outputMapping={
                "accessToken": "${RES_BODY(access_token)}",
                "tokenType": "${RES_BODY(token_type)}",
                "expiresIn": "${RES_BODY(expires_in)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockGetAccountDetail",
            sourceName="Mock 查询账户详情",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/accounts/10001",
            method=HttpMethod.GET,
            requestMapping={
                "headers": {"Accept": "application/json", "X-Trace-Id": "seed-demo-trace"},
                "query": {"expand": "profile,roles", "locale": "zh-CN"},
                "authConfig": {"type": "bearer", "token": "mock-token-for-local-test"},
                "bodyType": "none",
            },
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "accountId": "${RES_BODY(data.id)}",
                "accountName": "${RES_BODY(data.name)}",
                "department": "${RES_BODY(data.profile.department)}",
                "traceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockCreateUser",
            sourceName="Mock 创建用户",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/users",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "application/json", "Content-Type": "application/json", "X-Operator": "datagen-seed"},
                "query": {"dryRun": "false"},
                "authConfig": {"type": "bearer", "token": "mock-token-for-local-test"},
                "bodyType": "raw-json",
                "rawBody": json.dumps(
                    {
                        "tenantId": "T10001",
                        "user": {"name": "王五", "age": 31, "enabled": True},
                        "tags": ["seed", "mock"],
                    },
                    ensure_ascii=False,
                ),
            },
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "createdUserId": "${RES_BODY(data.userId)}",
                "createdUserName": "${RES_BODY(data.name)}",
                "tenantId": "${RES_BODY(data.tenantId)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockQueryDictionary",
            sourceName="Mock 查询用户状态字典",
            sysCode=HTTP_SYS_CODE,
            path="/openapi/v1/dictionaries",
            method=HttpMethod.GET,
            requestMapping={
                "headers": {"Accept": "application/json", "X-Api-Version": "2026-06"},
                "query": {"dictType": "USER_STATUS"},
                "authConfig": {"type": "apikey", "key": "api_key", "value": "mock-api-key-xyz789", "addTo": "query"},
                "bodyType": "none",
            },
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "dictType": "${RES_BODY(data.dictType)}",
                "firstCode": "${RES_BODY(data.items[0].code)}",
                "firstLabel": "${RES_BODY(data.items[0].label)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockGetUserListWithHeaders",
            sourceName="Mock 查询用户列表 Header/Query",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/users",
            method=HttpMethod.GET,
            requestMapping={
                "headers": {
                    "Accept": "application/json",
                    "X-Tenant-Id": "T10001",
                    "X-Request-Id": "seed-user-list-001",
                },
                "query": {"pageNo": "1", "pageSize": "20", "keyword": "张", "includeDisabled": "false"},
                "authConfig": {"type": "none"},
                "bodyType": "none",
            },
            responseHeadersSchema=[
                schema_field("x-trace-id", "Trace ID", InputFieldType.STRING, "响应追踪 ID"),
            ],
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "total": "${RES_BODY(data.total)}",
                "firstUserId": "${RES_BODY(data.list[0].userId)}",
                "firstUserName": "${RES_BODY(data.list[0].name)}",
                "traceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockSessionLoginCookie",
            sourceName="Mock 登录并提取 Cookie",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/session/login",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "application/json", "Content-Type": "application/json", "X-Tenant-Id": "T10001"},
                "authConfig": {"type": "none"},
                "bodyType": "raw-json",
                "rawBody": json.dumps(
                    {"tenantId": "T10001", "username": "demo_user", "password": "demo_password"},
                    ensure_ascii=False,
                ),
            },
            bodySchema=[
                schema_field("tenantId", "租户 ID", InputFieldType.STRING, "登录租户编码", default="T10001"),
                schema_field("username", "用户名", InputFieldType.STRING, "登录用户名", default="demo_user"),
                schema_field("password", "密码", InputFieldType.STRING, "登录密码", default="demo_password"),
            ],
            responseHeadersSchema=[
                schema_field("x-trace-id", "Trace ID", InputFieldType.STRING, "响应追踪 ID"),
            ],
            responseCookiesSchema=[
                schema_field("session_id", "会话 Cookie", InputFieldType.STRING, "服务端 Set-Cookie 写入的会话 ID"),
                schema_field("csrf_token", "CSRF Cookie", InputFieldType.STRING, "服务端 Set-Cookie 写入的 CSRF Token"),
            ],
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "sessionId": "${RES_COOKIE(session_id)}",
                "csrfToken": "${RES_COOKIE(csrf_token)}",
                "loginUser": "${RES_BODY(data.username)}",
                "tenantId": "${RES_BODY(data.tenantId)}",
                "traceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockSoapCreateOrderXml",
            sourceName="Mock SOAP XML 创建订单",
            sysCode=HTTP_SYS_CODE,
            path="/soap/orders/create",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "application/xml", "Content-Type": "application/xml", "X-Source": "datagen-seed"},
                "query": {"validateOnly": "true"},
                "authConfig": {"type": "basic", "username": "soap-client", "password": "soap-secret"},
                "bodyType": "raw-xml",
                "rawBody": (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    "<CreateOrderRequest>\n"
                    "  <tenantId>T10001</tenantId>\n"
                    "  <orderNo>T202606060001</orderNo>\n"
                    "  <amount>299.00</amount>\n"
                    "</CreateOrderRequest>"
                ),
            },
            bodySchema=[
                schema_field("tenantId", "租户 ID", InputFieldType.STRING, "XML 请求租户编码", default="T10001"),
                schema_field("orderNo", "订单号", InputFieldType.STRING, "XML 请求订单号", default="T202606060001"),
                schema_field("amount", "订单金额", InputFieldType.NUMBER, "XML 请求订单金额", default=299.00),
            ],
            responseSchema=[
                schema_field("success", "是否成功", InputFieldType.BOOLEAN, "XML 响应成功标记"),
                schema_field("orderId", "订单 ID", InputFieldType.STRING, "XML 响应订单 ID"),
                schema_field("orderNo", "订单号", InputFieldType.STRING, "XML 响应订单号"),
                schema_field("status", "订单状态", InputFieldType.STRING, "XML 响应订单状态"),
            ],
            responseHeadersSchema=[
                schema_field("x-trace-id", "Trace ID", InputFieldType.STRING, "XML 响应追踪 ID"),
            ],
            responseHandling=status_only_response_handling("XML"),
            outputMapping={
                "xmlTraceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockSendTextMessage",
            sourceName="Mock 纯文本发送消息",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/messages/text",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "text/plain", "Content-Type": "text/plain", "X-Api-Key": "mock-api-key-xyz789", "X-Tenant-Id": "T10001"},
                "query": {"channel": "sms"},
                "authConfig": {"type": "apikey", "key": "X-Api-Key", "value": "mock-api-key-xyz789", "addTo": "header"},
                "bodyType": "raw-text",
                "rawBody": "用户 ${input.userId} 的订单 ${input.orderNo} 已进入造数流程。",
            },
            bodySchema=[
                schema_field("messageText", "消息文本", InputFieldType.STRING, "纯文本请求体样例"),
            ],
            responseSchema=[
                schema_field("success", "成功标记", InputFieldType.STRING, "TEXT 响应中的 success 行"),
                schema_field("messageId", "消息 ID", InputFieldType.STRING, "TEXT 响应中的 messageId 行"),
                schema_field("status", "消息状态", InputFieldType.STRING, "TEXT 响应中的 status 行"),
            ],
            responseHeadersSchema=[
                schema_field("x-trace-id", "Trace ID", InputFieldType.STRING, "TEXT 响应追踪 ID"),
            ],
            responseHandling=status_only_response_handling("TEXT"),
            outputMapping={
                "textTraceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
        HttpSourceConfig(
            sourceCode="mockUploadFileFormData",
            sourceName="Mock FormData 上传文件",
            sysCode=HTTP_SYS_CODE,
            path="/api/v1/files/upload",
            method=HttpMethod.POST,
            requestMapping={
                "headers": {"Accept": "application/json"},
                "query": {"folder": "seed-demo"},
                "authConfig": {"type": "bearer", "token": "mock-token-for-local-test"},
                "bodyType": "form-data",
                "formData": [
                    {"key": "file", "value": "seed-demo.txt", "enabled": True},
                    {"key": "bizType", "value": "DATAGEN_SCENE", "enabled": True},
                    {"key": "overwrite", "value": "false", "enabled": True},
                ],
            },
            responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
            outputMapping={
                "fileId": "${RES_BODY(data.fileId)}",
                "fileName": "${RES_BODY(data.fileName)}",
                "downloadUrl": "${RES_BODY(data.downloadUrl)}",
                "traceId": "${RES_HEADER(x-trace-id)}",
            },
            status=ConfigStatus.ENABLED,
        ),
    ]


def success_response_handling(path: str, op: str, value: Any) -> dict[str, Any]:
    return {
        "expectedContentType": "JSON",
        "statusCode": {"success": [200]},
        "businessSuccess": {"allOf": [{"path": f"${{{path}}}", "op": op, "value": value}]},
        "businessFailure": {"anyOf": []},
    }


def status_only_response_handling(expected_content_type: str) -> dict[str, Any]:
    return {
        "expectedContentType": expected_content_type,
        "statusCode": {"success": [200]},
        "businessSuccess": {"allOf": []},
        "businessFailure": {"anyOf": []},
    }


def schema_field(
    name: str,
    label: str,
    field_type: InputFieldType,
    remark: str,
    *,
    default: Any = None,
    required: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": field_type,
        "required": required,
        "defaultValue": default,
        "remark": remark,
        "batchEnabled": False,
    }


def sql_parameter(
    name: str,
    field_type: InputFieldType,
    required: bool,
    default_value: Any,
    description: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": field_type,
        "required": required,
        "defaultValue": default_value,
        "description": description,
    }


async def upsert_scene(scene_service: SceneService, scene: SceneDefinition) -> None:
    try:
        await scene_service.update_scene(scene.sceneCode, scene, operator=OPERATOR)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        await scene_service.create_scene(scene, operator=OPERATOR)


async def upsert_and_publish_scene(scene_service: SceneService, scene: SceneDefinition) -> None:
    await upsert_scene(scene_service, scene)
    await scene_service.publish_scene(scene.sceneCode, operator=OPERATOR)


def build_integration_draft_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="mock_http_sqlite_integration",
        sceneName="Mock HTTP + SQLite 综合联调场景",
        sceneType="demo",
        sceneRemark="包含 HTTP mock server 步骤和 SQLite mock 数据库步骤，用于验证新多态步骤模型的保存、回显和单步测试。",
        inputSchema=common_input_schema(),
        steps=[
            http_token_step(position=Position(x=80, y=80)),
            http_account_step(position=Position(x=360, y=80)),
            sql_member_step(position=Position(x=80, y=260)),
            sql_inventory_step(position=Position(x=360, y=260)),
            sql_insert_log_step(
                depends_on=["sql_query_member", "sql_query_inventory"],
                remark="${steps.sql_query_inventory.outputs.productName} 库存 ${steps.sql_query_inventory.outputs.stockNum}",
                position=Position(x=640, y=260),
            ),
        ],
        resultMapping={
            "accountName": "${steps.http_account_detail.outputs.accountName}",
            "memberStatus": "${steps.sql_query_member.outputs.accountStatus}",
            "productName": "${steps.sql_query_inventory.outputs.productName}",
            "stockNum": "${steps.sql_query_inventory.outputs.stockNum}",
            "logId": "${steps.sql_insert_order_log.outputs.logId}",
        },
        batchConfig=BatchConfig(enabled=False, maxConcurrency=1),
        status=SceneStatus.DRAFT,
    )


def build_sql_runnable_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="mock_sqlite_runnable_order_log",
        sceneName="Mock SQLite 可执行订单日志场景",
        sceneType="demo",
        sceneRemark="只包含 SQL 步骤，当前场景执行器可直接发布并执行。",
        inputSchema=common_input_schema(),
        steps=[
            sql_member_step(position=Position(x=80, y=80)),
            sql_inventory_step(position=Position(x=360, y=80)),
            sql_insert_log_step(
                depends_on=["sql_query_member", "sql_query_inventory"],
                remark="${steps.sql_query_member.outputs.memberLevel} 用户查询 ${steps.sql_query_inventory.outputs.productName}",
                position=Position(x=640, y=80),
            ),
        ],
        resultMapping={
            "accountStatus": "${steps.sql_query_member.outputs.accountStatus}",
            "memberLevel": "${steps.sql_query_member.outputs.memberLevel}",
            "productName": "${steps.sql_query_inventory.outputs.productName}",
            "stockNum": "${steps.sql_query_inventory.outputs.stockNum}",
            "logId": "${steps.sql_insert_order_log.outputs.logId}",
            "affectedRows": "${steps.sql_insert_order_log.outputs.affectedRows}",
        },
        batchConfig=BatchConfig(enabled=False, maxConcurrency=1),
        status=SceneStatus.DRAFT,
    )


def build_full_stack_complex_scene() -> SceneDefinition:
    return SceneDefinition(
        sceneCode="mock_full_stack_http_sql_complex",
        sceneName="Mock HTTP/SQL 复杂变量编排场景",
        sceneType="demo",
        sceneRemark="覆盖 HTTP JSON/XML/TEXT/FormData/Header/Cookie 和复杂 SQL 查询，并在最终输出中展示多节点变量引用结果。",
        inputSchema=common_input_schema()
        + [
            input_field("tenantId", "租户 ID", InputFieldType.STRING, "T10001", True),
            input_field("quantity", "购买数量", InputFieldType.NUMBER, 1, True),
            input_field("category", "商品分类", InputFieldType.STRING, "electronics", True),
            input_field("lowStockThreshold", "低库存阈值", InputFieldType.NUMBER, 10, True),
            input_field("vipAmount", "高价值阈值", InputFieldType.NUMBER, 500, True),
            input_field("messageChannel", "消息渠道", InputFieldType.STRING, "sms", True),
        ],
        steps=[
            http_token_step(position=Position(x=80, y=80)),
            http_session_login_step(position=Position(x=320, y=80)),
            http_account_step(position=Position(x=560, y=80)),
            http_user_list_step(position=Position(x=800, y=80)),
            sql_member_step(position=Position(x=80, y=280)),
            sql_inventory_step(position=Position(x=320, y=280)),
            sql_order_aggregate_complex_step(position=Position(x=560, y=280)),
            sql_inventory_risk_complex_step(position=Position(x=800, y=280)),
            http_xml_create_order_step(position=Position(x=80, y=500)),
            http_text_message_step(position=Position(x=320, y=500)),
            http_upload_form_data_step(position=Position(x=560, y=500)),
            sql_insert_log_step(
                depends_on=[
                    "http_account_detail",
                    "http_text_message",
                    "http_upload_form_data",
                    "sql_order_aggregate_complex",
                    "sql_inventory_risk_complex",
                ],
                remark=(
                    "复杂场景汇总：用户 ${steps.sql_query_member.outputs.userId}/"
                    "${steps.http_account_detail.outputs.accountName}，商品 ${steps.sql_query_inventory.outputs.productName}，"
                    "库存风险 ${steps.sql_inventory_risk_complex.outputs.inventoryRisk}，"
                    "消息 trace ${steps.http_text_message.outputs.textTraceId}，"
                    "文件 ${steps.http_upload_form_data.outputs.fileId}"
                ),
                position=Position(x=800, y=500),
            ),
        ],
        resultSchema=[
            schema_field("summary", "执行摘要", InputFieldType.STRING, "多节点变量拼接后的业务摘要"),
            schema_field("sessionId", "会话 ID", InputFieldType.STRING, "HTTP Cookie 提取结果"),
            schema_field("csrfToken", "CSRF Token", InputFieldType.STRING, "HTTP Cookie 提取结果"),
            schema_field("accountName", "账户名称", InputFieldType.STRING, "HTTP JSON 响应提取结果"),
            schema_field("firstUserName", "用户列表首项", InputFieldType.STRING, "HTTP Header/Query 接口响应提取结果"),
            schema_field("xmlTraceId", "XML Trace ID", InputFieldType.STRING, "XML 接口响应 Header 提取结果"),
            schema_field("textTraceId", "TEXT Trace ID", InputFieldType.STRING, "TEXT 接口响应 Header 提取结果"),
            schema_field("fileId", "上传文件 ID", InputFieldType.STRING, "FormData 接口响应提取结果"),
            schema_field("memberLevel", "会员等级", InputFieldType.STRING, "SQL 查询输出"),
            schema_field("inventoryRisk", "库存风险", InputFieldType.STRING, "复杂 SQL CASE 输出"),
            schema_field("paidAmount", "已支付金额", InputFieldType.NUMBER, "复杂 SQL CTE 聚合输出"),
            schema_field("logId", "日志 ID", InputFieldType.NUMBER, "最终 SQL 写日志输出"),
        ],
        resultMapping={
            "summary": (
                "用户 ${steps.sql_query_member.outputs.userId}(${steps.http_account_detail.outputs.accountName}) "
                "使用 session ${steps.http_session_login.outputs.sessionId} 处理订单 ${input.orderNo}，"
                "商品 ${steps.sql_query_inventory.outputs.productName} 库存 ${steps.sql_query_inventory.outputs.stockNum}，"
                "风险 ${steps.sql_inventory_risk_complex.outputs.inventoryRisk}，日志 ${steps.sql_insert_order_log.outputs.logId}"
            ),
            "sessionId": "${steps.http_session_login.outputs.sessionId}",
            "csrfToken": "${steps.http_session_login.outputs.csrfToken}",
            "accountName": "${steps.http_account_detail.outputs.accountName}",
            "firstUserName": "${steps.http_user_list.outputs.firstUserName}",
            "xmlTraceId": "${steps.http_xml_create_order.outputs.xmlTraceId}",
            "textTraceId": "${steps.http_text_message.outputs.textTraceId}",
            "fileId": "${steps.http_upload_form_data.outputs.fileId}",
            "memberLevel": "${steps.sql_query_member.outputs.memberLevel}",
            "accountStatus": "${steps.sql_query_member.outputs.accountStatus}",
            "productName": "${steps.sql_query_inventory.outputs.productName}",
            "salePrice": "${steps.sql_query_inventory.outputs.salePrice}",
            "inventoryRisk": "${steps.sql_inventory_risk_complex.outputs.inventoryRisk}",
            "availableNum": "${steps.sql_inventory_risk_complex.outputs.availableNum}",
            "paidCount": "${steps.sql_order_aggregate_complex.outputs.paidCount}",
            "paidAmount": "${steps.sql_order_aggregate_complex.outputs.paidAmount}",
            "valueTag": "${steps.sql_order_aggregate_complex.outputs.valueTag}",
            "logId": "${steps.sql_insert_order_log.outputs.logId}",
            "affectedRows": "${steps.sql_insert_order_log.outputs.affectedRows}",
        },
        batchConfig=BatchConfig(enabled=False, maxConcurrency=1),
        status=SceneStatus.DRAFT,
    )


def common_input_schema() -> list[dict[str, Any]]:
    return [
        input_field("env", "环境编码", InputFieldType.STRING, "dev", True),
        input_field("accountId", "账户 ID", InputFieldType.STRING, "10001", True),
        input_field("userId", "用户 ID", InputFieldType.STRING, "U10001", True),
        input_field("skuId", "商品 SKU", InputFieldType.STRING, "SKU10001", True),
        input_field("orderNo", "订单号", InputFieldType.STRING, "T202606060001", True),
        input_field("actionType", "日志动作", InputFieldType.STRING, "SEED_SCENE_RUN", True),
        input_field("remark", "日志备注", InputFieldType.STRING, "由 datagen 新模型 seed 场景写入", False),
    ]


def input_field(
    name: str,
    label: str,
    field_type: InputFieldType,
    default_value: Any,
    required: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": field_type,
        "required": required,
        "defaultValue": default_value,
        "batchEnabled": False,
    }


def default_timeout_config() -> dict[str, int]:
    return {
        "connectTimeoutSeconds": 5,
        "readTimeoutSeconds": 10,
        "writeTimeoutSeconds": 10,
        "poolTimeoutSeconds": 5,
    }


def http_token_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_get_token",
        stepName="HTTP 获取 mock token",
        type="HTTP",
        enabled=True,
        dependsOn=[],
        position=position,
        sourceName="Mock OAuth 获取 Token",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.POST,
        path="/oauth/token",
        timeoutConfig={
            "connectTimeoutSeconds": 5,
            "readTimeoutSeconds": 10,
            "writeTimeoutSeconds": 10,
            "poolTimeoutSeconds": 5,
        },
        requestMapping={
            "headers": {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            "authConfig": {"type": "basic", "username": "mock-client", "password": "mock-secret"},
            "bodyType": "x-www-form-urlencoded",
            "urlEncodedData": {
                "grant_type": "password",
                "username": "${input.userId}",
                "password": "demo_password",
                "scope": "account:user",
            },
        },
        responseHandling=success_response_handling("RES_BODY(access_token)", "NOT_EMPTY", ""),
        outputMapping={
            "accessToken": "${RES_BODY(access_token)}",
            "tokenType": "${RES_BODY(token_type)}",
            "expiresIn": "${RES_BODY(expires_in)}",
        },
    )


def http_account_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_account_detail",
        stepName="HTTP 查询 mock 账户详情",
        type="HTTP",
        enabled=True,
        dependsOn=["http_get_token"],
        position=position,
        sourceName="Mock 查询账户详情",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.GET,
        path="/api/v1/accounts/10001",
        timeoutConfig={
            "connectTimeoutSeconds": 5,
            "readTimeoutSeconds": 10,
            "writeTimeoutSeconds": 10,
            "poolTimeoutSeconds": 5,
        },
        requestMapping={
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer ${steps.http_get_token.outputs.accessToken}",
            },
            "query": {"expand": "profile,roles", "locale": "zh-CN"},
            "authConfig": {"type": "none"},
            "bodyType": "none",
        },
        responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
        outputMapping={
            "accountId": "${RES_BODY(data.id)}",
            "accountName": "${RES_BODY(data.name)}",
            "department": "${RES_BODY(data.profile.department)}",
        },
    )


def http_session_login_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_session_login",
        stepName="HTTP 登录并提取 Cookie",
        type="HTTP",
        enabled=True,
        dependsOn=["http_get_token"],
        position=position,
        sourceName="Mock 登录并提取 Cookie",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.POST,
        path="/api/v1/session/login",
        timeoutConfig=default_timeout_config(),
        requestMapping={
            "headers": {"Accept": "application/json", "Content-Type": "application/json", "X-Tenant-Id": "${input.tenantId}"},
            "authConfig": {"type": "none"},
            "bodyType": "raw-json",
            "rawBody": json.dumps(
                {
                    "tenantId": "${input.tenantId}",
                    "username": "${input.userId}",
                    "password": "demo_password",
                },
                ensure_ascii=False,
            ),
        },
        responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
        outputMapping={
            "sessionId": "${RES_COOKIE(session_id)}",
            "csrfToken": "${RES_COOKIE(csrf_token)}",
            "loginUser": "${RES_BODY(data.username)}",
            "tenantId": "${RES_BODY(data.tenantId)}",
            "traceId": "${RES_HEADER(x-trace-id)}",
        },
    )


def http_user_list_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_user_list",
        stepName="HTTP 查询用户列表 Header/Cookie",
        type="HTTP",
        enabled=True,
        dependsOn=["http_session_login"],
        position=position,
        sourceName="Mock 查询用户列表 Header/Query",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.GET,
        path="/api/v1/users",
        timeoutConfig=default_timeout_config(),
        requestMapping={
            "headers": {
                "Accept": "application/json",
                "X-Tenant-Id": "${steps.http_session_login.outputs.tenantId}",
                "X-Request-Id": "scene-${input.orderNo}",
                "X-Csrf-Token": "${steps.http_session_login.outputs.csrfToken}",
                "Cookie": "session_id=${steps.http_session_login.outputs.sessionId}; csrf_token=${steps.http_session_login.outputs.csrfToken}",
            },
            "query": {"pageNo": "1", "pageSize": "20", "keyword": "张", "includeDisabled": "false"},
            "authConfig": {"type": "none"},
            "bodyType": "none",
        },
        responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
        outputMapping={
            "total": "${RES_BODY(data.total)}",
            "firstUserId": "${RES_BODY(data.list[0].userId)}",
            "firstUserName": "${RES_BODY(data.list[0].name)}",
            "traceId": "${RES_HEADER(x-trace-id)}",
        },
    )


def http_xml_create_order_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_xml_create_order",
        stepName="HTTP XML 创建订单",
        type="HTTP",
        enabled=True,
        dependsOn=["http_get_token", "sql_query_inventory", "sql_order_aggregate_complex"],
        position=position,
        sourceName="Mock SOAP XML 创建订单",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.POST,
        path="/soap/orders/create",
        timeoutConfig=default_timeout_config(),
        requestMapping={
            "headers": {"Accept": "application/xml", "Content-Type": "application/xml", "X-Source": "datagen-scene"},
            "query": {"validateOnly": "true"},
            "authConfig": {"type": "basic", "username": "soap-client", "password": "soap-secret"},
            "bodyType": "raw-xml",
            "rawBody": (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                "<CreateOrderRequest>\n"
                "  <tenantId>${input.tenantId}</tenantId>\n"
                "  <orderNo>${input.orderNo}</orderNo>\n"
                "  <skuId>${steps.sql_query_inventory.outputs.skuId}</skuId>\n"
                "  <amount>${steps.sql_query_inventory.outputs.salePrice}</amount>\n"
                "  <memberLevel>${steps.sql_query_member.outputs.memberLevel}</memberLevel>\n"
                "  <valueTag>${steps.sql_order_aggregate_complex.outputs.valueTag}</valueTag>\n"
                "</CreateOrderRequest>"
            ),
        },
        responseHandling=status_only_response_handling("XML"),
        outputMapping={
            "xmlTraceId": "${RES_HEADER(x-trace-id)}",
        },
    )


def http_text_message_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_text_message",
        stepName="HTTP TEXT 发送通知",
        type="HTTP",
        enabled=True,
        dependsOn=["http_xml_create_order", "sql_inventory_risk_complex"],
        position=position,
        sourceName="Mock 纯文本发送消息",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.POST,
        path="/api/v1/messages/text",
        timeoutConfig=default_timeout_config(),
        requestMapping={
            "headers": {"Accept": "text/plain", "Content-Type": "text/plain", "X-Api-Key": "mock-api-key-xyz789", "X-Tenant-Id": "${input.tenantId}"},
            "query": {"channel": "${input.messageChannel}"},
            "authConfig": {"type": "apikey", "key": "X-Api-Key", "value": "mock-api-key-xyz789", "addTo": "header"},
            "bodyType": "raw-text",
            "rawBody": (
                "订单 ${input.orderNo} 已完成 XML 校验，用户 ${steps.sql_query_member.outputs.userId}，"
                "商品 ${steps.sql_query_inventory.outputs.productName}，库存风险 ${steps.sql_inventory_risk_complex.outputs.inventoryRisk}。"
            ),
        },
        responseHandling=status_only_response_handling("TEXT"),
        outputMapping={
            "textTraceId": "${RES_HEADER(x-trace-id)}",
        },
    )


def http_upload_form_data_step(*, position: Position) -> HttpStepDefinition:
    return HttpStepDefinition(
        stepId="http_upload_form_data",
        stepName="HTTP FormData 上传证明文件",
        type="HTTP",
        enabled=True,
        dependsOn=["http_get_token", "http_text_message"],
        position=position,
        sourceName="Mock FormData 上传文件",
        sysCode=HTTP_SYS_CODE,
        method=HttpMethod.POST,
        path="/api/v1/files/upload",
        timeoutConfig=default_timeout_config(),
        requestMapping={
            "headers": {"Accept": "application/json"},
            "query": {"folder": "scene-${input.orderNo}"},
            "authConfig": {"type": "bearer", "token": "${steps.http_get_token.outputs.accessToken}"},
            "bodyType": "form-data",
            "formData": [
                {"key": "file", "value": "scene-${input.orderNo}.txt", "enabled": True},
                {"key": "bizType", "value": "DATAGEN_SCENE", "enabled": True},
                {"key": "overwrite", "value": "true", "enabled": True},
            ],
        },
        responseHandling=success_response_handling("RES_BODY(success)", "EQ", True),
        outputMapping={
            "fileId": "${RES_BODY(data.fileId)}",
            "fileName": "${RES_BODY(data.fileName)}",
            "downloadUrl": "${RES_BODY(data.downloadUrl)}",
            "traceId": "${RES_HEADER(x-trace-id)}",
        },
    )


def sql_member_step(*, position: Position) -> SqlStepDefinition:
    sql_text = "SELECT user_id, mobile, member_level, account_status, points FROM member_account WHERE user_id = :userId"
    return SqlStepDefinition(
        stepId="sql_query_member",
        stepName="SQL 查询会员状态",
        type="SQL",
        enabled=True,
        dependsOn=[],
        position=position,
        sourceName="Mock 查询会员账户状态",
        sysCode=TRADE_SYS_CODE,
        datasourceCode=TRADE_DATASOURCE_CODE,
        operation=SqlOperation.SELECT,
        sqlText=sql_text,
        normalizedSql=sql_text,
        parameters=[{"name": "userId", "type": "string", "required": True, "defaultValue": "U10001", "description": "会员用户 ID"}],
        safety=SqlSourceSafety(requireWhere=True),
        paramMapping={"userId": "${input.userId}"},
        outputMapping={
            "userId": "${SQL_RESULT(row.user_id)}",
            "accountStatus": "${SQL_RESULT(row.account_status)}",
            "memberLevel": "${SQL_RESULT(row.member_level)}",
            "mobile": "${SQL_RESULT(row.mobile)}",
            "points": "${SQL_RESULT(row.points)}",
        },
    )


def sql_inventory_step(*, position: Position) -> SqlStepDefinition:
    sql_text = (
        "SELECT p.sku_id, p.product_name, p.sale_price, i.stock_num, i.locked_num, i.status "
        "FROM product_sku p JOIN inventory i ON p.sku_id = i.sku_id WHERE p.sku_id = :skuId"
    )
    return SqlStepDefinition(
        stepId="sql_query_inventory",
        stepName="SQL 查询商品库存",
        type="SQL",
        enabled=True,
        dependsOn=[],
        position=position,
        sourceName="Mock 按 SKU 查询库存",
        sysCode=TRADE_SYS_CODE,
        datasourceCode=TRADE_DATASOURCE_CODE,
        operation=SqlOperation.SELECT,
        sqlText=sql_text,
        normalizedSql=sql_text,
        parameters=[{"name": "skuId", "type": "string", "required": True, "defaultValue": "SKU10001", "description": "商品 SKU 编码"}],
        safety=SqlSourceSafety(requireWhere=True),
        paramMapping={"skuId": "${input.skuId}"},
        outputMapping={
            "skuId": "${SQL_RESULT(row.sku_id)}",
            "productName": "${SQL_RESULT(row.product_name)}",
            "salePrice": "${SQL_RESULT(row.sale_price)}",
            "stockNum": "${SQL_RESULT(row.stock_num)}",
            "lockedNum": "${SQL_RESULT(row.locked_num)}",
            "inventoryStatus": "${SQL_RESULT(row.status)}",
        },
    )


def sql_order_aggregate_complex_step(*, position: Position) -> SqlStepDefinition:
    sql_text = (
        "WITH paid_orders AS ("
        "  SELECT user_id, COUNT(*) AS paid_count, SUM(order_amount) AS paid_amount "
        "  FROM trade_order WHERE order_status = :paidStatus GROUP BY user_id"
        ") "
        "SELECT m.user_id, m.member_level, m.account_status, "
        "       COALESCE(p.paid_count, 0) AS paid_count, "
        "       COALESCE(p.paid_amount, 0) AS paid_amount, "
        "       CASE WHEN COALESCE(p.paid_amount, 0) >= :vipAmount THEN 'HIGH_VALUE' ELSE 'NORMAL_VALUE' END AS value_tag "
        "FROM member_account m "
        "LEFT JOIN paid_orders p ON p.user_id = m.user_id "
        "WHERE m.user_id = :userId AND m.account_status IN ('ACTIVE', 'FROZEN')"
    )
    return SqlStepDefinition(
        stepId="sql_order_aggregate_complex",
        stepName="SQL 复杂聚合订单概览",
        type="SQL",
        enabled=True,
        dependsOn=["sql_query_member"],
        position=position,
        sourceName="Mock 复杂聚合查询订单概览",
        sysCode=TRADE_SYS_CODE,
        datasourceCode=TRADE_DATASOURCE_CODE,
        operation=SqlOperation.SELECT,
        sqlText=sql_text,
        normalizedSql=sql_text,
        parameters=[
            {"name": "paidStatus", "type": "string", "required": True, "defaultValue": "PAID", "description": "纳入聚合统计的订单状态"},
            {"name": "vipAmount", "type": "number", "required": True, "defaultValue": 500, "description": "高价值用户订单金额阈值"},
            {"name": "userId", "type": "string", "required": True, "defaultValue": "U10001", "description": "会员用户 ID"},
        ],
        safety=SqlSourceSafety(requireWhere=True),
        paramMapping={
            "paidStatus": "PAID",
            "vipAmount": "${input.vipAmount}",
            "userId": "${steps.sql_query_member.outputs.userId}",
        },
        outputMapping={
            "userId": "${SQL_RESULT(row.user_id)}",
            "memberLevel": "${SQL_RESULT(row.member_level)}",
            "accountStatus": "${SQL_RESULT(row.account_status)}",
            "paidCount": "${SQL_RESULT(row.paid_count)}",
            "paidAmount": "${SQL_RESULT(row.paid_amount)}",
            "valueTag": "${SQL_RESULT(row.value_tag)}",
        },
    )


def sql_inventory_risk_complex_step(*, position: Position) -> SqlStepDefinition:
    sql_text = (
        "SELECT p.sku_id, p.product_name, p.category, i.stock_num, i.locked_num, "
        "       (i.stock_num - i.locked_num) AS available_num, "
        "       CASE "
        "         WHEN p.status <> 'ON_SALE' THEN 'OFFLINE' "
        "         WHEN (i.stock_num - i.locked_num) <= :lowStockThreshold THEN 'RISK' "
        "         ELSE 'OK' "
        "       END AS inventory_risk, "
        "       EXISTS(SELECT 1 FROM trade_order o WHERE o.sku_id = p.sku_id AND o.order_status = :orderStatus) AS has_paid_order "
        "FROM product_sku p "
        "JOIN inventory i ON i.sku_id = p.sku_id "
        "WHERE p.category = :category AND p.sku_id = :skuId"
    )
    return SqlStepDefinition(
        stepId="sql_inventory_risk_complex",
        stepName="SQL 复杂库存风险判断",
        type="SQL",
        enabled=True,
        dependsOn=["sql_query_inventory"],
        position=position,
        sourceName="Mock 复杂库存风险查询",
        sysCode=TRADE_SYS_CODE,
        datasourceCode=TRADE_DATASOURCE_CODE,
        operation=SqlOperation.SELECT,
        sqlText=sql_text,
        normalizedSql=sql_text,
        parameters=[
            {"name": "lowStockThreshold", "type": "number", "required": True, "defaultValue": 10, "description": "低库存阈值"},
            {"name": "orderStatus", "type": "string", "required": True, "defaultValue": "PAID", "description": "判断历史订单的状态"},
            {"name": "category", "type": "string", "required": True, "defaultValue": "electronics", "description": "商品分类"},
            {"name": "skuId", "type": "string", "required": True, "defaultValue": "SKU10001", "description": "商品 SKU 编码"},
        ],
        safety=SqlSourceSafety(requireWhere=True),
        paramMapping={
            "lowStockThreshold": "${input.lowStockThreshold}",
            "orderStatus": "PAID",
            "category": "${input.category}",
            "skuId": "${steps.sql_query_inventory.outputs.skuId}",
        },
        outputMapping={
            "skuId": "${SQL_RESULT(row.sku_id)}",
            "productName": "${SQL_RESULT(row.product_name)}",
            "category": "${SQL_RESULT(row.category)}",
            "availableNum": "${SQL_RESULT(row.available_num)}",
            "inventoryRisk": "${SQL_RESULT(row.inventory_risk)}",
            "hasPaidOrder": "${SQL_RESULT(row.has_paid_order)}",
        },
    )


def sql_insert_log_step(
    *,
    depends_on: list[str],
    remark: str,
    position: Position,
) -> SqlStepDefinition:
    sql_text = (
        "INSERT INTO order_log(order_no, user_id, action_type, remark, created_at) "
        "VALUES (:orderNo, :userId, :actionType, :remark, CURRENT_TIMESTAMP)"
    )
    return SqlStepDefinition(
        stepId="sql_insert_order_log",
        stepName="SQL 写入订单日志",
        type="SQL",
        enabled=True,
        dependsOn=depends_on,
        position=position,
        sourceName="Mock 写入订单日志",
        sysCode=TRADE_SYS_CODE,
        datasourceCode=TRADE_DATASOURCE_CODE,
        operation=SqlOperation.INSERT,
        sqlText=sql_text,
        normalizedSql=sql_text,
        parameters=[
            {"name": "orderNo", "type": "string", "required": True, "defaultValue": "T202606060001", "description": "订单号"},
            {"name": "userId", "type": "string", "required": True, "defaultValue": "U10001", "description": "用户 ID"},
            {"name": "actionType", "type": "string", "required": True, "defaultValue": "SEED_SCENE_RUN", "description": "操作类型"},
            {"name": "remark", "type": "string", "required": False, "defaultValue": "seed log", "description": "日志备注"},
        ],
        safety=SqlSourceSafety(requireWhere=False, maxAffectedRows=1),
        paramMapping={
            "orderNo": "${input.orderNo}",
            "userId": "${input.userId}",
            "actionType": "${input.actionType}",
            "remark": remark,
        },
        outputMapping={
            "logId": "${SQL_RESULT(lastInsertId)}",
            "affectedRows": "${SQL_RESULT(affectedRows)}",
        },
    )


if __name__ == "__main__":
    main()
