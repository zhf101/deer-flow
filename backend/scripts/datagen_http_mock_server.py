r"""Datagen HTTP 配置测试数据 mock 服务。

该脚本服务于前端 HTTP 接口配置页面联调：它从本地 SQLite 数据库读取
``SYS_HTTP_TEST`` 系统下的 HTTP 接口配置，并按配置里的 method/path 提供
可调用的 mock 接口。

启动示例：
    .\.venv\Scripts\python.exe scripts\datagen_http_mock_server.py --sync-endpoints
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

DEFAULT_DB_PATH = Path(".deer-flow/data/deerflow.db")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18080
TEST_SYS_CODE = "SYS_HTTP_TEST"


@dataclass(frozen=True)
class MockRoute:
    """从 HTTP 接口配置表加载出的 mock 路由。"""

    source_code: str
    source_name: str
    method: str
    path: str
    request_mapping: dict[str, Any]
    response_schema: list[dict[str, Any]]
    response_handling: dict[str, Any]
    output_mapping: dict[str, str]
    path_regex: re.Pattern[str]


def _load_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _compile_path(path: str) -> re.Pattern[str]:
    """把配置里的 ``/users/${inputs.id}`` 转成可匹配任意 path segment 的正则。"""

    escaped = re.escape(path)
    escaped = re.sub(r"\\\$\\\{[^}]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _load_routes(db_path: Path, sys_code: str) -> list[MockRoute]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            select source_code, source_name, method, path, request_mapping_json,
                   response_schema_json, response_handling_json, output_mapping_json
            from df_http_source
            where sys_code = ? and status = 'ENABLED'
            order by source_code asc
            """,
            (sys_code,),
        ).fetchall()
    finally:
        con.close()

    return [
        MockRoute(
            source_code=row[0],
            source_name=row[1],
            method=row[2].upper(),
            path=row[3],
            request_mapping=_load_json(row[4], {}),
            response_schema=_load_json(row[5], []),
            response_handling=_load_json(row[6], {}),
            output_mapping=_load_json(row[7], {}),
            path_regex=_compile_path(row[3]),
        )
        for row in rows
    ]


def _sync_service_endpoints(db_path: Path, sys_code: str, base_url: str) -> None:
    """把测试系统的服务端点改成本地 mock 服务地址。"""

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "update df_service_endpoint set base_url = ?, updated_at = datetime('now') where sys_code = ?",
            (base_url, sys_code),
        )
        con.commit()
    finally:
        con.close()


def _value_from_field(field: dict[str, Any]) -> Any:
    typ = field.get("type")
    default = field.get("defaultValue")
    children = field.get("children") or []

    if typ == "object":
        return {child["name"]: _value_from_field(child) for child in children}
    if typ == "array":
        if children:
            return [_value_from_field(children[0])]
        return []
    if typ == "number":
        try:
            return int(default) if str(default).isdigit() else float(default)
        except (TypeError, ValueError):
            return 0
    if typ == "boolean":
        if isinstance(default, bool):
            return default
        return str(default).lower() == "true"
    return "" if default is None else default


def _schema_to_json_object(schema: list[dict[str, Any]]) -> dict[str, Any]:
    return {field["name"]: _value_from_field(field) for field in schema}


async def _request_body(request: Request) -> Any:
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    if "application/json" in content_type:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        return {key: str(value) for key, value in form.items()}
    return text


def _request_summary(request: Request, route: MockRoute, body: Any) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "headers": {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            in {
                "accept",
                "authorization",
                "content-type",
                "x-api-key",
                "x-api-version",
                "x-operator",
                "x-request-id",
                "x-source",
                "x-tenant-id",
                "x-trace-id",
            }
        },
        "authConfig": route.request_mapping.get("authConfig", {"type": "none"}),
        "bodyType": route.request_mapping.get("bodyType", "none"),
        "body": body,
    }


def _json_response(route: MockRoute, request: Request, body: Any) -> JSONResponse:
    payload = _schema_to_json_object(route.response_schema)
    if not payload:
        payload = {"success": True, "data": {"id": f"mock-{route.source_code}"}}
    payload.setdefault("success", True)
    payload.setdefault("mock", {})
    payload["mock"] = {
        "sourceCode": route.source_code,
        "sourceName": route.source_name,
        "request": _request_summary(request, route, body),
        "outputMapping": route.output_mapping,
    }
    return JSONResponse(payload, headers={"X-Trace-Id": f"mock-trace-{route.source_code}"})


def _xml_response(route: MockRoute, request: Request, body: Any) -> Response:
    source = route.source_code
    request_summary = _request_summary(request, route, body)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<MockResponse>
  <success>true</success>
  <sourceCode>{source}</sourceCode>
  <sourceName>{route.source_name}</sourceName>
  <orderId>mock-order-10001</orderId>
  <method>{request.method}</method>
  <path>{request.url.path}</path>
  <bodyType>{request_summary["bodyType"]}</bodyType>
</MockResponse>"""
    return Response(content=content, media_type="application/xml", headers={"X-Trace-Id": f"mock-trace-{source}"})


def _text_response(route: MockRoute, request: Request, body: Any) -> PlainTextResponse:
    text = (
        f"success=true\n"
        f"sourceCode={route.source_code}\n"
        f"sourceName={route.source_name}\n"
        f"method={request.method}\n"
        f"path={request.url.path}\n"
        f"bodyType={route.request_mapping.get('bodyType', 'none')}\n"
        f"body={body if body is not None else ''}\n"
    )
    return PlainTextResponse(text, headers={"X-Trace-Id": f"mock-trace-{route.source_code}"})


def _response_for(route: MockRoute, request: Request, body: Any) -> Response:
    expected = (route.response_handling.get("expectedContentType") or "JSON").upper()
    if expected == "XML":
        return _xml_response(route, request, body)
    if expected == "TEXT":
        return _text_response(route, request, body)
    return _json_response(route, request, body)


def create_app(db_path: Path, sys_code: str = TEST_SYS_CODE) -> FastAPI:
    """创建独立 mock FastAPI 应用。"""

    routes = _load_routes(db_path, sys_code)
    app = FastAPI(title="Datagen HTTP Mock Server", version="0.1.0")
    app.state.mock_routes = routes

    @app.get("/__mock/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "sysCode": sys_code, "routeCount": len(app.state.mock_routes)}

    @app.get("/__mock/routes")
    async def list_routes() -> list[dict[str, Any]]:
        return [
            {
                "sourceCode": route.source_code,
                "sourceName": route.source_name,
                "method": route.method,
                "path": route.path,
                "bodyType": route.request_mapping.get("bodyType", "none"),
                "authType": (route.request_mapping.get("authConfig") or {}).get("type", "none"),
                "queryKeys": list((route.request_mapping.get("query") or {}).keys()),
                "headerKeys": list((route.request_mapping.get("headers") or {}).keys()),
            }
            for route in app.state.mock_routes
        ]

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def mock_dispatch(path: str, request: Request) -> Response:
        request_path = "/" + path
        route = next(
            (
                item
                for item in app.state.mock_routes
                if item.method == request.method.upper() and item.path_regex.match(request_path)
            ),
            None,
        )
        if route is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "errorCode": "MOCK_ROUTE_NOT_FOUND",
                    "errorMessage": f"No mock route for {request.method} {request_path}",
                    "availableRoutes": [
                        {"method": item.method, "path": item.path, "sourceCode": item.source_code}
                        for item in app.state.mock_routes
                    ],
                },
            )
        body = await _request_body(request)
        return _response_for(route, request, body)

    return app


def create_default_app() -> FastAPI:
    """uvicorn factory 入口，使用默认数据库和测试系统编码。"""

    return create_app(DEFAULT_DB_PATH, TEST_SYS_CODE)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start datagen HTTP mock server.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 数据库路径。")
    parser.add_argument("--host", default=DEFAULT_HOST, help="监听地址。")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口。")
    parser.add_argument("--sys-code", default=TEST_SYS_CODE, help="要加载的系统编码。")
    parser.add_argument(
        "--sync-endpoints",
        action="store_true",
        help="启动前把该系统的服务端点 baseUrl 更新为当前 mock 服务地址。",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    db_path = args.db
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    base_url = f"http://{args.host}:{args.port}"
    if args.sync_endpoints:
        _sync_service_endpoints(db_path, args.sys_code, base_url)
        print(f"Synced df_service_endpoint for {args.sys_code} to {base_url}")

    app = create_app(db_path, args.sys_code)
    print(f"Loaded {len(app.state.mock_routes)} mock routes for {args.sys_code}")
    print(f"Route list: {base_url}/__mock/routes")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
