"""将 df_http_source 表中 SYS_HTTP_TEST 系统的接口配置导出为 Postman Collection v2.1 格式。"""

import json
import sqlite3
import uuid
from pathlib import Path

DB_PATH = Path(".deer-flow/data/deerflow.db")
OUTPUT_PATH = Path("datagen_http_mock.postman_collection.json")
SYS_CODE = "SYS_HTTP_TEST"
BASE_URL = "http://127.0.0.1:18080"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT source_code, source_name, method, path, request_mapping_json,
               response_schema_json, response_handling_json, output_mapping_json
        FROM df_http_source
        WHERE sys_code = ? AND status = 'ENABLED'
        ORDER BY source_code
        """,
        (SYS_CODE,),
    ).fetchall()

    items = []
    for row in rows:
        rm = json.loads(row["request_mapping_json"])
        rh = json.loads(row["response_handling_json"]) if row["response_handling_json"] else {}
        om = json.loads(row["output_mapping_json"]) if row["output_mapping_json"] else {}
        rs = json.loads(row["response_schema_json"]) if row["response_schema_json"] else []

        item = _build_request(row, rm, rh, om, rs)
        items.append(item)

    collection = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": "Datagen HTTP Mock 接口集合",
            "description": "从 df_http_source 表导出的 SYS_HTTP_TEST 系统 mock 接口，base_url: " + BASE_URL,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": BASE_URL, "type": "string"},
            {"key": "api_key", "value": "mock-api-key-xyz789", "type": "string"},
            {"key": "access_token", "value": "mock-access-token-abc123", "type": "string"},
            {"key": "tenant_id", "value": "T10001", "type": "string"},
        ],
        "item": items,
    }

    OUTPUT_PATH.write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"已导出 {len(items)} 个接口到 {OUTPUT_PATH}")
    conn.close()


def _build_request(row, rm, rh, om, rs):
    """构建单个 Postman request 对象。"""
    source_code = row["source_code"]
    source_name = row["source_name"]
    method = row["method"].upper()
    path = row["path"]

    # URL
    url = {
        "raw": "{{base_url}}" + path,
        "host": ["{{base_url}}"],
        "path": [seg for seg in path.split("/") if seg],
    }

    # Query 参数
    query = rm.get("query") or {}
    if query:
        url["query"] = [
            {"key": k, "value": v, "description": (rm.get("_queryDesc") or {}).get(k, "")}
            for k, v in query.items()
        ]

    # Headers
    headers = []
    for k, v in (rm.get("headers") or {}).items():
        desc = (rm.get("_headersDesc") or {}).get(k, "")
        headers.append({"key": k, "value": v, "description": desc, "type": "text"})

    # Auth
    auth = _build_auth(rm.get("authConfig") or {"type": "none"})

    # Body
    body = _build_body(rm)

    # 构建 request 对象
    request_obj = {
        "method": method,
        "header": headers,
        "url": url,
        "auth": auth,
        "description": f"来源: {source_code}\n系统: {SYS_CODE}\n内容类型: {rm.get('bodyType', 'none')}",
    }
    if body is not None:
        request_obj["body"] = body

    # 响应示例
    response_example = _build_response_example(source_code, source_name, rh, rs, om)

    return {
        "name": source_name,
        "request": request_obj,
        "response": [response_example] if response_example else [],
        "event": _build_events(source_code, rh, om),
    }


def _build_auth(auth_config):
    """转换 authConfig 为 Postman auth 格式。"""
    auth_type = auth_config.get("type", "none")

    if auth_type == "bearer":
        return {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
        }

    if auth_type == "basic":
        return {
            "type": "basic",
            "basic": [
                {"key": "username", "value": auth_config.get("username", ""), "type": "string"},
                {"key": "password", "value": auth_config.get("password", ""), "type": "string"},
            ],
        }

    if auth_type == "apikey":
        return {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": auth_config.get("key", ""), "type": "string"},
                {"key": "value", "value": auth_config.get("value", ""), "type": "string"},
                {"key": "in", "value": auth_config.get("addTo", "header"), "type": "string"},
            ],
        }

    return {"type": "noauth"}


def _build_body(rm):
    """转换 request_mapping_json 为 Postman body 格式。"""
    body_type = rm.get("bodyType", "none")

    if body_type == "none":
        return None

    if body_type == "raw-json":
        raw = rm.get("rawBody", "")
        return {
            "mode": "raw",
            "raw": raw,
            "options": {"raw": {"language": "json"}},
        }

    if body_type == "raw-xml":
        raw = rm.get("rawBody", "")
        return {
            "mode": "raw",
            "raw": raw,
            "options": {"raw": {"language": "xml"}},
        }

    if body_type == "raw-text":
        raw = rm.get("rawBody", "")
        return {
            "mode": "raw",
            "raw": raw,
            "options": {"raw": {"language": "text"}},
        }

    if body_type == "form-data":
        form_data = []
        for item in rm.get("formData", []):
            form_data.append({
                "key": item["key"],
                "value": item["value"],
                "description": item.get("description", ""),
                "type": "text",
                "disabled": not item.get("enabled", True),
            })
        return {"mode": "formdata", "formdata": form_data}

    if body_type == "x-www-form-urlencoded":
        url_encoded = []
        for k, v in (rm.get("urlEncodedData") or {}).items():
            desc = (rm.get("_urlEncodedDesc") or {}).get(k, "")
            url_encoded.append({"key": k, "value": v, "description": desc})
        return {"mode": "urlencoded", "urlencoded": url_encoded}

    return None


def _build_response_example(source_code, source_name, rh, rs, om):
    """构建 Postman 响应示例。"""
    expected_ct = (rh.get("expectedContentType") or "JSON").upper()
    status_codes = (rh.get("statusCode") or {}).get("success", [200])
    status_code = status_codes[0] if status_codes else 200

    # 构建响应体
    if expected_ct == "JSON":
        payload = _schema_to_json(rs)
        if not payload:
            payload = {"success": True, "data": {"id": f"mock-{source_code}"}}
        payload.setdefault("success", True)
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        content_type = "application/json"
    elif expected_ct == "XML":
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<MockResponse>\n"
            f"  <success>true</success>\n"
            f"  <sourceCode>{source_code}</sourceCode>\n"
            f"  <sourceName>{source_name}</sourceName>\n"
            f"  <orderId>mock-order-10001</orderId>\n"
            "</MockResponse>"
        )
        content_type = "application/xml"
    else:
        body = f"success=true\nsourceCode={source_code}\nsourceName={source_name}\n"
        content_type = "text/plain"

    return {
        "name": f"{source_name} - 成功响应",
        "originalRequest": {
            "method": "POST",
            "header": [],
            "url": {"raw": "{{base_url}}/placeholder", "host": ["{{base_url}}"], "path": ["placeholder"]},
        },
        "status": f"{status_code} {_status_text(status_code)}",
        "code": status_code,
        "_postman_previewlanguage": "json" if expected_ct == "JSON" else "xml",
        "header": [
            {"key": "Content-Type", "value": content_type},
            {"key": "X-Trace-Id", "value": f"mock-trace-{source_code}"},
        ],
        "cookie": [],
        "body": body,
    }


def _schema_to_json(schema):
    """将 response_schema 转为 JSON 对象。"""
    if not schema:
        return {}
    result = {}
    for field in schema:
        result[field["name"]] = _field_value(field)
    return result


def _field_value(field):
    """从 schema 字段提取值。"""
    typ = field.get("type", "string")
    default = field.get("defaultValue")
    children = field.get("children") or []

    if typ == "object":
        return {child["name"]: _field_value(child) for child in children}
    if typ == "array":
        return [_field_value(children[0])] if children else []
    if typ == "number":
        try:
            return int(default) if str(default).isdigit() else float(default)
        except (TypeError, ValueError):
            return 0
    if typ == "boolean":
        if isinstance(default, bool):
            return default
        return str(default).lower() == "true"
    return default if default is not None else ""


def _status_text(code):
    """HTTP 状态码文本。"""
    texts = {200: "OK", 201: "Created", 202: "Accepted", 204: "No Content", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 500: "Internal Server Error"}
    return texts.get(code, "OK")


def _build_events(source_code, rh, om):
    """构建 pre-request 和 test 脚本。"""
    events = []

    # Pre-request Script: 生成动态变量
    events.append({
        "listen": "prerequest",
        "script": {
            "type": "text/javascript",
            "exec": [
                "// 自动生成动态变量",
                "pm.variables.set('request_id', 'req-' + Date.now());",
                "pm.variables.set('trace_id', 'trace-' + Date.now());",
                "pm.variables.set('timestamp', new Date().toISOString());",
            ],
        },
    })

    # Test Script: 验证响应
    test_lines = [
        "// 自动验证响应",
        f"pm.test('{source_code} - 状态码校验', function () {{",
        f"    pm.expect(pm.response.code).to.be.oneOf({json.dumps((rh.get('statusCode') or {}).get('success', [200]))});",
        "});",
    ]

    expected_ct = (rh.get("expectedContentType") or "JSON").upper()
    if expected_ct == "JSON":
        test_lines += [
            f"pm.test('{source_code} - 响应为 JSON', function () {{",
            "    pm.response.to.have.header('Content-Type', 'application/json');",
            "    const json = pm.response.json();",
            "    pm.expect(json).to.have.property('success');",
            "});",
        ]
        # output_mapping 注释
        if om:
            for key, expression in om.items():
                if _is_supported_output_expression(expression):
                    test_lines.append(f"// 输出映射: {key} <- {expression}")
    elif expected_ct == "XML":
        test_lines += [
            f"pm.test('{source_code} - 响应为 XML', function () {{",
            "    pm.response.to.have.header('Content-Type', 'application/xml');",
            "});",
        ]
    else:
        test_lines += [
            f"pm.test('{source_code} - 响应为文本', function () {{",
            "    pm.response.to.have.header('Content-Type', 'text/plain');",
            "});",
        ]

    events.append({
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": test_lines,
        },
    })

    return events


def _is_supported_output_expression(expression):
    """Postman 注释仅展示当前 HTTP 输出表达式。"""
    return (
        isinstance(expression, str)
        and (
            expression.startswith("${RES_BODY(")
            or expression.startswith("${RES_HEADER(")
            or expression.startswith("${RES_COOKIE(")
        )
    )


if __name__ == "__main__":
    main()
