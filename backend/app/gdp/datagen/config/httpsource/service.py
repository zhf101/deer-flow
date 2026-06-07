"""HTTP 源业务服务层。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from time import perf_counter
from traceback import format_exception
from typing import TypeVar
from urllib.parse import urljoin

from fastapi import HTTPException
import httpx

from app.gdp.datagen.config.base.repository import BaseConfigNotFoundError, BaseConfigRepository
from app.gdp.datagen.config.common.models import ConfigStatus
from app.gdp.datagen.config.httpsource.models import (
    DisableResponse,
    HttpSourceConfig,
    HttpSourceResponse,
    HttpSourceTestErrorInfo,
    HttpSourceTestRequest,
    HttpSourceTestRequestInfo,
    HttpSourceTestResponse,
    HttpSourceTestResponseInfo,
)
from app.gdp.datagen.config.httpsource.repository import (
    HttpSourceConflictError,
    HttpSourceNotFoundError,
    HttpSourceRepository,
)

T = TypeVar("T")


class HttpSourceService:
    def __init__(self, repository: HttpSourceRepository, base_repository: BaseConfigRepository) -> None:
        self._repo = repository
        self._base_repo = base_repository

    async def list_http_sources(
        self,
        *,
        sys_code: str | None = None,
        status: ConfigStatus | None = None,
    ) -> list[HttpSourceResponse]:
        return await self._repo.list_http_sources(sys_code=sys_code, status=status)

    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        return await self._guard(lambda: self._repo.get_http_source(source_code))

    async def upsert_http_source(self, config: HttpSourceConfig, *, operator: str | None = None) -> HttpSourceResponse:
        await self._validate_enabled_system(config.sysCode)
        return await self._guard(lambda: self._repo.upsert_http_source(config, operator=operator))

    async def disable_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.disable_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def delete_http_source(self, source_code: str, *, operator: str | None = None) -> DisableResponse:
        await self._guard(lambda: self._repo.delete_http_source(source_code, operator=operator))
        return DisableResponse(success=True)

    async def test_http_source(self, request: HttpSourceTestRequest) -> HttpSourceTestResponse:
        """真实执行一次 HTTP 接口配置测试请求。"""

        config = request.config
        try:
            endpoint = await self._base_repo.get_enabled_service_endpoint(env_code=request.envCode, sys_code=config.sysCode)
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"enabled service endpoint not found: {request.envCode}/{config.sysCode}") from exc

        request_info = _build_request_info(endpoint.baseUrl, config)
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request.timeoutSeconds, follow_redirects=False) as client:
                response = await client.request(
                    request_info.method,
                    request_info.url,
                    headers=request_info.headers,
                    content=_request_content(request_info),
                    data=_request_form_data(request_info),
                    files=_request_files(request_info),
                )
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            return HttpSourceTestResponse(
                success=True,
                request=request_info,
                response=HttpSourceTestResponseInfo(
                    statusCode=response.status_code,
                    headers=dict(response.headers),
                    body=_response_body(response),
                    elapsedMs=elapsed_ms,
                ),
            )
        except Exception as exc:
            elapsed_ms = round((perf_counter() - started) * 1000, 3)
            return HttpSourceTestResponse(
                success=False,
                request=request_info,
                response=HttpSourceTestResponseInfo(elapsedMs=elapsed_ms),
                error=HttpSourceTestErrorInfo(
                    type=type(exc).__name__,
                    message=str(exc),
                    detail="".join(format_exception(type(exc), exc, exc.__traceback__)),
                ),
            )

    async def _validate_enabled_system(self, sys_code: str) -> None:
        try:
            system = await self._base_repo.get_system(sys_code)
        except BaseConfigNotFoundError as exc:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}") from exc
        if system.status != ConfigStatus.ENABLED:
            raise HTTPException(status_code=422, detail=f"enabled system not found: {sys_code}")

    async def _guard(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            return await call()
        except HttpSourceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HttpSourceConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def _build_request_info(base_url: str, config: HttpSourceConfig) -> HttpSourceTestRequestInfo:
    mapping = config.requestMapping or {}
    query = _string_map(mapping.get("query"))
    headers = _string_map(mapping.get("headers"))
    auth = mapping.get("authConfig") if isinstance(mapping.get("authConfig"), dict) else {"type": "none"}
    _apply_auth(headers, query, auth)

    body_type = str(mapping.get("bodyType") or "none")
    body = None if config.method == "GET" else _request_body(mapping, body_type)
    url = _join_url(base_url, config.path)
    if query:
        url = str(httpx.URL(url).copy_merge_params(query))
    return HttpSourceTestRequestInfo(
        url=url,
        method=config.method.value,
        headers=headers,
        query=query,
        body=body,
        bodyType=body_type,
    )


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): "" if val is None else str(val) for key, val in value.items()}


def _apply_auth(headers: dict[str, str], query: dict[str, str], auth: object) -> None:
    if not isinstance(auth, dict):
        return
    auth_type = auth.get("type")
    if auth_type == "bearer" and auth.get("token"):
        headers["Authorization"] = f"Bearer {auth['token']}"
    elif auth_type == "basic" and auth.get("username"):
        headers["Authorization"] = f"Basic {{{{{auth.get('username')}:{auth.get('password') or ''}}}}}"
    elif auth_type == "apikey" and auth.get("key"):
        key = str(auth["key"])
        value = "" if auth.get("value") is None else str(auth.get("value"))
        if auth.get("addTo") == "query":
            query[key] = value
        else:
            headers[key] = value


def _request_body(mapping: dict[str, object], body_type: str) -> object:
    if body_type == "raw-json":
        raw_body = mapping.get("rawBody")
        if isinstance(raw_body, str) and raw_body.strip():
            try:
                return json.loads(raw_body)
            except json.JSONDecodeError:
                return raw_body
        return _tree_to_object(mapping.get("bodyTree"))
    if body_type in {"raw-text", "raw-xml"}:
        return mapping.get("rawBody") or ""
    if body_type == "form-data":
        rows = mapping.get("formData")
        if not isinstance(rows, list):
            return {}
        return {str(row.get("key")): "" if row.get("value") is None else str(row.get("value")) for row in rows if isinstance(row, dict) and row.get("enabled", True) and row.get("key")}
    if body_type == "x-www-form-urlencoded":
        return _string_map(mapping.get("urlEncodedData"))
    return None


def _tree_to_object(value: object) -> object:
    if not isinstance(value, list):
        return {}
    result: dict[str, object] = {}
    for item in value:
        if isinstance(item, dict) and item.get("name"):
            result[str(item["name"])] = _tree_value(item)
    return result


def _tree_value(field: dict[str, object]) -> object:
    field_type = field.get("type")
    children = field.get("children")
    default = field.get("defaultValue")
    if field_type == "object":
        return _tree_to_object(children)
    if field_type == "array":
        if isinstance(children, list) and children:
            return [_tree_value(children[0])]
        return []
    if field_type == "number":
        try:
            text = str(default)
            return int(text) if text.isdigit() else float(text)
        except (TypeError, ValueError):
            return default
    if field_type == "boolean":
        if isinstance(default, bool):
            return default
        return str(default).lower() == "true"
    return default


def _request_content(request_info: HttpSourceTestRequestInfo) -> bytes | str | None:
    if request_info.method == "GET":
        return None
    if request_info.bodyType == "raw-json":
        if isinstance(request_info.body, str):
            return request_info.body
        return json.dumps(request_info.body, ensure_ascii=False).encode("utf-8")
    if request_info.bodyType in {"raw-text", "raw-xml"}:
        return "" if request_info.body is None else str(request_info.body)
    return None


def _request_form_data(request_info: HttpSourceTestRequestInfo) -> dict[str, str] | None:
    if request_info.bodyType == "x-www-form-urlencoded" and isinstance(request_info.body, dict):
        return {str(key): "" if value is None else str(value) for key, value in request_info.body.items()}
    return None


def _request_files(request_info: HttpSourceTestRequestInfo) -> dict[str, tuple[None, str]] | None:
    if request_info.bodyType == "form-data" and isinstance(request_info.body, dict):
        return {
            str(key): (None, "" if value is None else str(value))
            for key, value in request_info.body.items()
        }
    return None


def _response_body(response: httpx.Response) -> object:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return response.json()
        except ValueError:
            pass
    return response.text
