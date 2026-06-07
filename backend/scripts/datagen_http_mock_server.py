"""Datagen HTTP 接口 Mock 服务。

为前端 HTTP 接口配置页面提供可调用的 mock 接口。
每个接口独立定义路由处理函数，返回真实业务结构的 mock 数据。

启动方式:
    python scripts/datagen_http_mock_server.py
    python scripts/datagen_http_mock_server.py --sync-endpoints  # 同时更新 df_service_endpoint 的 baseUrl
    python scripts/datagen_http_mock_server.py --port 19000       # 自定义端口

启动后访问:
    http://127.0.0.1:18080/__mock/routes   — 查看所有已注册路由
    http://127.0.0.1:18080/__mock/health   — 健康检查
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

# ============================================================
# 常量
# ============================================================

DEFAULT_DB_PATH = Path(".deer-flow/data/deerflow.db")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080
TEST_SYS_CODE = "SYS_HTTP_TEST"

# ============================================================
# 日志配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mock-server")


# ============================================================
# 工具函数
# ============================================================


def _log_request(method: str, path: str, headers: dict[str, str], body: Any = None) -> None:
    """打印收到的请求详情。"""
    log.info(">>> %s %s", method, path)
    log.info("    Headers: %s", json.dumps(headers, ensure_ascii=False))
    if body is not None:
        if isinstance(body, str):
            log.info("    Body(text): %s", body[:200])
        else:
            log.info("    Body(json): %s", json.dumps(body, ensure_ascii=False)[:200])


def _log_response(method: str, path: str, status: int, summary: str) -> None:
    """打印返回的响应摘要。"""
    log.info("<<< %s %s -> %d %s", method, path, status, summary)


def _trace_id(tag: str) -> str:
    """生成 mock 追踪 ID。"""
    return f"mock-trace-{tag}-{int(time.time())}"


def _important_headers(request: Request) -> dict[str, str]:
    """提取请求中值得关注的 header。"""
    keys = {
        "accept", "content-type", "authorization",
        "x-api-key", "x-api-version", "x-operator",
        "x-request-id", "x-source", "x-tenant-id", "x-trace-id",
    }
    return {k: v for k, v in request.headers.items() if k.lower() in keys}


async def _read_body_text(request: Request) -> str | None:
    """读取请求体为文本。"""
    raw = await request.body()
    return raw.decode("utf-8", errors="replace") if raw else None


async def _read_body_json(request: Request) -> dict | None:
    """读取请求体为 JSON 对象。"""
    text = await _read_body_text(request)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _sync_service_endpoints(db_path: Path, sys_code: str, base_url: str) -> None:
    """把 df_service_endpoint 表中该系统的 baseUrl 更新为 mock 服务地址。"""
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "UPDATE df_service_endpoint SET base_url = ?, updated_at = datetime('now') WHERE sys_code = ?",
            (base_url, sys_code),
        )
        con.commit()
        log.info("已同步 df_service_endpoint: %s -> %s", sys_code, base_url)
    finally:
        con.close()


# ============================================================
# 创建 FastAPI 应用 — 每个接口独立注册
# ============================================================


def create_app() -> FastAPI:
    app = FastAPI(title="Datagen HTTP Mock Server", version="2.0.0")

    # ----------------------------------------------------------
    # 管理接口
    # ----------------------------------------------------------

    @app.get("/__mock/health")
    async def health():
        return {"ok": True, "version": "2.0.0"}

    @app.get("/__mock/routes")
    async def list_routes():
        """列出所有已注册的 mock 路由。"""
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        routes.append({"method": method, "path": route.path})
        return routes

    # ----------------------------------------------------------
    # 1. GET /api/v1/users
    #    认证: 无
    #    Query: pageNo, pageSize, keyword, includeDisabled
    #    Header: Accept, X-Tenant-Id, X-Request-Id
    #    Body: 无
    # ----------------------------------------------------------

    @app.get("/api/v1/users")
    async def get_user_list(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        _log_request("GET", "/api/v1/users", headers)

        response = {
            "success": True,
            "data": {
                "total": 2,
                "pageNo": int(params.get("pageNo", 1)),
                "pageSize": int(params.get("pageSize", 20)),
                "list": [
                    {"userId": "U10001", "name": "张三", "age": 28, "enabled": True, "tenantId": "T10001"},
                    {"userId": "U10002", "name": "李四", "age": 35, "enabled": True, "tenantId": "T10001"},
                ],
            },
            "errorCode": "",
            "errorMessage": "",
        }
        resp_headers = {"X-Trace-Id": _trace_id("user-list")}
        _log_response("GET", "/api/v1/users", 200, f"返回 {response['data']['total']} 条用户")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 2. GET /api/v1/accounts/{accountId}
    #    认证: Bearer Token (Header Authorization)
    #    Query: expand, locale
    #    Header: Accept, Authorization, X-Trace-Id
    #    Body: 无
    # ----------------------------------------------------------

    @app.get("/api/v1/accounts/{account_id}")
    async def get_account_detail(account_id: str, request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        auth = headers.get("authorization", "")
        _log_request("GET", f"/api/v1/accounts/{account_id}", headers)
        log.info("    认证: Bearer %s", "***" if auth.startswith("Bearer ") else "缺失!")

        response = {
            "success": True,
            "data": {
                "id": account_id,
                "name": "张三",
                "email": "zhangsan@example.com",
                "phone": "13800138000",
                "profile": {
                    "department": "技术部",
                    "title": "高级工程师",
                    "joinedAt": "2023-06-01",
                },
                "roles": ["user", "admin"],
                "locale": params.get("locale", "zh-CN"),
            },
            "errorCode": "",
            "errorMessage": "",
        }
        resp_headers = {"X-Trace-Id": _trace_id("account-detail")}
        _log_response("GET", f"/api/v1/accounts/{account_id}", 200, f"返回账户 {account_id} 详情")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 3. GET /openapi/v1/dictionaries
    #    认证: API Key (Query 参数 api_key)
    #    Query: dictType, api_key
    #    Header: Accept, X-Api-Version
    #    Body: 无
    # ----------------------------------------------------------

    @app.get("/openapi/v1/dictionaries")
    async def get_dictionary(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        dict_type = params.get("dictType", "UNKNOWN")
        api_key = params.get("api_key", "")
        _log_request("GET", "/openapi/v1/dictionaries", headers)
        log.info("    认证: API Key(Query) %s", "***" if api_key else "缺失!")
        log.info("    字典类型: %s", dict_type)

        # 根据字典类型返回不同的 mock 数据
        dict_data = {
            "USER_STATUS": [
                {"code": "ACTIVE", "label": "正常", "sort": 1},
                {"code": "DISABLED", "label": "停用", "sort": 2},
                {"code": "LOCKED", "label": "锁定", "sort": 3},
            ],
            "ORDER_STATUS": [
                {"code": "PENDING", "label": "待支付", "sort": 1},
                {"code": "PAID", "label": "已支付", "sort": 2},
                {"code": "SHIPPED", "label": "已发货", "sort": 3},
                {"code": "COMPLETED", "label": "已完成", "sort": 4},
            ],
        }
        items = dict_data.get(dict_type, [{"code": "MOCK", "label": "mock值", "sort": 1}])

        response = {
            "success": True,
            "data": {
                "dictType": dict_type,
                "items": items,
            },
            "errorCode": "",
            "errorMessage": "",
        }
        resp_headers = {"X-Trace-Id": _trace_id("dict"), "X-Api-Version": headers.get("x-api-version", "")}
        _log_response("GET", "/openapi/v1/dictionaries", 200, f"返回字典 {dict_type} 共 {len(items)} 项")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 4. POST /api/v1/users
    #    认证: Bearer Token (Header Authorization)
    #    Query: dryRun
    #    Header: Content-Type, Accept, Authorization, X-Operator
    #    Body: JSON — { tenantId, user: { name, age, enabled }, tags }
    # ----------------------------------------------------------

    @app.post("/api/v1/users")
    async def create_user(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        body = await _read_body_json(request)
        _log_request("POST", "/api/v1/users", headers, body)
        log.info("    认证: Bearer %s", "***" if headers.get("authorization", "").startswith("Bearer ") else "缺失!")
        log.info("    dryRun: %s", params.get("dryRun", "false"))

        # 从请求体提取数据
        tenant_id = (body or {}).get("tenantId", "T10001")
        user_info = (body or {}).get("user", {})
        user_name = user_info.get("name", "未知")

        response = {
            "success": True,
            "data": {
                "userId": "U" + str(int(time.time()))[-5:],
                "tenantId": tenant_id,
                "name": user_name,
                "age": user_info.get("age", 0),
                "enabled": user_info.get("enabled", True),
                "tags": (body or {}).get("tags", []),
                "createdAt": "2026-06-07T12:00:00",
            },
        }
        resp_headers = {"X-Trace-Id": _trace_id("create-user")}
        _log_response("POST", "/api/v1/users", 200, f"创建用户 {user_name} 成功")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 5. POST /soap/orders/create
    #    认证: Basic Auth (Header Authorization)
    #    Query: validateOnly
    #    Header: Content-Type=application/xml, Accept, Authorization, X-Source
    #    Body: XML — <CreateOrderRequest> { tenantId, orderNo, amount }
    # ----------------------------------------------------------

    @app.post("/soap/orders/create")
    async def create_order(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        body_text = await _read_body_text(request)
        _log_request("POST", "/soap/orders/create", headers, body_text)
        log.info("    认证: Basic %s", "***" if headers.get("authorization", "").startswith("Basic ") else "缺失!")
        log.info("    validateOnly: %s", params.get("validateOnly", "false"))

        # 简单解析 XML 中的字段（实际项目可用 xml.etree）
        order_no = "ORD-20260607-001"
        tenant_id = "T10001"
        if body_text:
            import re
            m = re.search(r"<orderNo>(.*?)</orderNo>", body_text)
            if m:
                order_no = m.group(1)
            m = re.search(r"<tenantId>(.*?)</tenantId>", body_text)
            if m:
                tenant_id = m.group(1)

        response_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<CreateOrderResponse>
  <success>true</success>
  <orderId>O{int(time.time()) % 100000:05d}</orderId>
  <orderNo>{order_no}</orderNo>
  <tenantId>{tenant_id}</tenantId>
  <status>PENDING</status>
  <createdAt>2026-06-07T12:00:00</createdAt>
</CreateOrderResponse>"""

        resp_headers = {"X-Trace-Id": _trace_id("create-order")}
        _log_response("POST", "/soap/orders/create", 200, f"创建订单 {order_no} 成功")
        return Response(content=response_xml, media_type="application/xml", headers=resp_headers)

    # ----------------------------------------------------------
    # 6. POST /api/v1/messages/text
    #    认证: API Key (Header X-Api-Key)
    #    Query: channel
    #    Header: Content-Type=text/plain, Accept, X-Api-Key, X-Tenant-Id
    #    Body: 纯文本
    # ----------------------------------------------------------

    @app.post("/api/v1/messages/text")
    async def send_text_message(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        body_text = await _read_body_text(request)
        _log_request("POST", "/api/v1/messages/text", headers, body_text)
        log.info("    认证: API Key(Header) %s", "***" if headers.get("x-api-key") else "缺失!")
        log.info("    渠道: %s", params.get("channel", "sms"))

        message_id = f"M{int(time.time()) % 100000:05d}"
        response = f"""success=true
messageId={message_id}
channel={params.get("channel", "sms")}
status=SENT
timestamp=2026-06-07T12:00:00"""

        resp_headers = {"X-Trace-Id": _trace_id("send-message")}
        _log_response("POST", "/api/v1/messages/text", 200, f"消息 {message_id} 发送成功")
        return PlainTextResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 7. POST /api/v1/files/upload
    #    认证: Bearer Token (Header Authorization)
    #    Query: folder
    #    Header: Accept, Authorization
    #    Body: multipart/form-data — file, bizType, overwrite
    # ----------------------------------------------------------

    @app.post("/api/v1/files/upload")
    async def upload_file(request: Request):
        headers = _important_headers(request)
        params = dict(request.query_params)
        _log_request("POST", "/api/v1/files/upload", headers)
        log.info("    认证: Bearer %s", "***" if headers.get("authorization", "").startswith("Bearer ") else "缺失!")
        log.info("    上传目录: %s", params.get("folder", "default"))

        # 读取 form-data 字段
        form = await request.form()
        file_name = "unknown"
        biz_type = "UNKNOWN"
        for key, value in form.items():
            if key == "file":
                # value 可能是 UploadFile 对象或字符串
                file_name = getattr(value, "filename", str(value))
            elif key == "bizType":
                biz_type = str(value)
            log.info("    form字段: %s = %s", key, value)

        file_id = f"F{int(time.time()) % 100000:05d}"
        response = {
            "success": True,
            "data": {
                "fileId": file_id,
                "fileName": file_name,
                "bizType": biz_type,
                "folder": params.get("folder", "default"),
                "size": 1024,
                "downloadUrl": f"/api/v1/files/{file_id}/download",
                "createdAt": "2026-06-07T12:00:00",
            },
            "errorCode": "",
            "errorMessage": "",
        }
        resp_headers = {"X-Trace-Id": _trace_id("upload")}
        _log_response("POST", "/api/v1/files/upload", 200, f"文件 {file_name} 上传成功 -> {file_id}")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 8. POST /oauth/token
    #    认证: Basic Auth (Header Authorization，客户端凭证)
    #    Header: Content-Type=application/x-www-form-urlencoded, Accept, Authorization
    #    Body: x-www-form-urlencoded — grant_type, username, password, scope
    # ----------------------------------------------------------

    @app.post("/oauth/token")
    async def oauth_token(request: Request):
        headers = _important_headers(request)
        _log_request("POST", "/oauth/token", headers)
        log.info("    认证: Basic %s", "***" if headers.get("authorization", "").startswith("Basic ") else "缺失!")

        # 读取 form 表单
        form = await request.form()
        form_data = {}
        for key, value in form.items():
            form_data[key] = str(value)
            log.info("    form字段: %s = %s", key, value if key != "password" else "***")

        username = form_data.get("username", "unknown")
        scope = form_data.get("scope", "")

        response = {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock-token-payload.signature",
            "token_type": "Bearer",
            "expires_in": 7200,
            "scope": scope,
            "username": username,
            "issued_at": "2026-06-07T12:00:00",
        }
        resp_headers = {"X-Trace-Id": _trace_id("oauth-token")}
        _log_response("POST", "/oauth/token", 200, f"用户 {username} 获取 Token 成功")
        return JSONResponse(response, headers=resp_headers)

    # ----------------------------------------------------------
    # 404 兜底 — 请求路径未匹配任何接口
    # ----------------------------------------------------------

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def catch_all(path: str, request: Request):
        request_path = "/" + path
        log.warning("!!! 未匹配: %s %s", request.method, request_path)

        registered = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for m in route.methods:
                    if m in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        registered.append(f"  {m:6s} {route.path}")

        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "errorCode": "MOCK_ROUTE_NOT_FOUND",
                "errorMessage": f"未找到 mock 路由: {request.method} {request_path}",
                "registeredRoutes": registered,
            },
        )

    return app


# ============================================================
# 启动入口
# ============================================================


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 Datagen HTTP Mock 服务")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 数据库路径")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口")
    parser.add_argument("--sync-endpoints", action="store_true", help="启动前同步 df_service_endpoint 的 baseUrl")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    db_path = args.db
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    base_url = f"http://{args.host}:{args.port}"

    if args.sync_endpoints:
        _sync_service_endpoints(db_path, TEST_SYS_CODE, base_url)

    app = create_app()

    # 打印路由表
    log.info("=" * 60)
    log.info("Datagen HTTP Mock Server 启动中...")
    log.info("监听地址: %s", base_url)
    log.info("数据库: %s", db_path)
    log.info("-" * 60)
    log.info("已注册接口:")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    log.info("  %s  %s", method, route.path)
    log.info("-" * 60)
    log.info("路由列表: %s/__mock/routes", base_url)
    log.info("健康检查: %s/__mock/health", base_url)
    log.info("=" * 60)

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
