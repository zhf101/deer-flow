"""修复 df_http_source 表中所有 ${} 变量引用为可直接调用 mock 服务的真实值。"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(".deer-flow/data/deerflow.db")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ============================================================
    # 1. http_get_params_headers_noauth
    # GET /api/v1/users — 查询用户列表（无认证）
    # ============================================================
    rm = {
        "query": {
            "pageNo": "1",
            "pageSize": "20",
            "keyword": "test",
            "includeDisabled": "false",
        },
        "_queryDesc": {
            "pageNo": "页码",
            "pageSize": "每页条数",
            "keyword": "搜索关键词",
            "includeDisabled": "是否包含停用用户",
        },
        "headers": {
            "Accept": "application/json",
            "X-Tenant-Id": "T10001",
            "X-Request-Id": "req-mock-001",
        },
        "_headersDesc": {
            "Accept": "响应类型",
            "X-Tenant-Id": "租户ID",
            "X-Request-Id": "请求追踪ID",
        },
        "authConfig": {"type": "none"},
        "bodyType": "none",
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_get_params_headers_noauth"),
    )
    print("Updated http_get_params_headers_noauth")

    # ============================================================
    # 2. http_get_bearer_auth
    # GET /api/v1/accounts/{accountId} — Bearer Auth 查询账户详情
    # ============================================================
    rm = {
        "query": {
            "expand": "profile,roles",
            "locale": "zh-CN",
        },
        "_queryDesc": {
            "expand": "展开字段",
            "locale": "界面语言",
        },
        "headers": {
            "Accept": "application/json",
            "Authorization": "Bearer mock-access-token-abc123",
            "X-Trace-Id": "trace-mock-001",
        },
        "_headersDesc": {
            "Authorization": "Bearer认证令牌",
            "X-Trace-Id": "链路ID",
        },
        "authConfig": {
            "type": "bearer",
            "token": "mock-access-token-abc123",
        },
        "bodyType": "none",
    }
    cur.execute(
        "UPDATE df_http_source SET path = ?, request_mapping_json = ? WHERE source_code = ?",
        ("/api/v1/accounts/10001", json.dumps(rm, ensure_ascii=False), "http_get_bearer_auth"),
    )
    print("Updated http_get_bearer_auth (path + request_mapping)")

    # ============================================================
    # 3. http_get_apikey_query_auth
    # GET /openapi/v1/dictionaries — API Key Query 认证查询字典值
    # ============================================================
    rm = {
        "query": {
            "dictType": "USER_STATUS",
            "api_key": "mock-api-key-xyz789",
        },
        "_queryDesc": {
            "dictType": "字典类型",
            "api_key": "Query认证Key",
        },
        "headers": {
            "Accept": "application/json",
            "X-Api-Version": "2026-06-06",
        },
        "_headersDesc": {
            "X-Api-Version": "接口版本",
        },
        "authConfig": {
            "type": "apikey",
            "key": "api_key",
            "value": "mock-api-key-xyz789",
            "addTo": "query",
        },
        "bodyType": "none",
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_get_apikey_query_auth"),
    )
    print("Updated http_get_apikey_query_auth")

    # ============================================================
    # 4. http_post_raw_json_bearer
    # POST /api/v1/users — Raw JSON + Bearer 创建用户
    # ============================================================
    rm = {
        "query": {
            "dryRun": "false",
        },
        "_queryDesc": {
            "dryRun": "是否只校验不入库",
        },
        "headers": {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer mock-access-token-abc123",
            "X-Operator": "admin",
        },
        "_headersDesc": {
            "Content-Type": "JSON内容类型",
            "X-Operator": "操作人",
        },
        "authConfig": {
            "type": "bearer",
            "token": "mock-access-token-abc123",
        },
        "bodyType": "raw-json",
        "bodyView": "tree",
        "bodyTree": [
            {
                "name": "tenantId",
                "label": "租户ID",
                "remark": None,
                "type": "string",
                "required": True,
                "defaultValue": "T10001",
                "optionsSource": None,
                "validation": None,
                "batchEnabled": False,
            },
            {
                "name": "user",
                "label": "用户信息",
                "remark": None,
                "type": "object",
                "required": True,
                "defaultValue": None,
                "optionsSource": None,
                "validation": None,
                "batchEnabled": False,
                "children": [
                    {
                        "name": "name",
                        "label": "姓名",
                        "remark": None,
                        "type": "string",
                        "required": True,
                        "defaultValue": "张三",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                    {
                        "name": "age",
                        "label": "年龄",
                        "remark": None,
                        "type": "number",
                        "required": True,
                        "defaultValue": "28",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                    {
                        "name": "enabled",
                        "label": "是否启用",
                        "remark": None,
                        "type": "boolean",
                        "required": True,
                        "defaultValue": "true",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                ],
            },
            {
                "name": "tags",
                "label": "标签列表",
                "remark": None,
                "type": "array",
                "required": False,
                "defaultValue": None,
                "optionsSource": None,
                "validation": None,
                "batchEnabled": False,
                "children": [
                    {
                        "name": "tag",
                        "label": "标签",
                        "remark": None,
                        "type": "string",
                        "required": True,
                        "defaultValue": "vip",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    }
                ],
            },
        ],
        "rawBody": '{\n  "tenantId": "T10001",\n  "user": {\n    "name": "张三",\n    "age": 28,\n    "enabled": true\n  },\n  "tags": ["vip"]\n}',
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_post_raw_json_bearer"),
    )
    print("Updated http_post_raw_json_bearer")

    # ============================================================
    # 5. http_post_raw_xml_basic
    # POST /soap/orders/create — Raw XML + Basic Auth 创建订单
    # ============================================================
    rm = {
        "query": {
            "validateOnly": "false",
        },
        "_queryDesc": {
            "validateOnly": "是否只校验",
        },
        "headers": {
            "Content-Type": "application/xml",
            "Accept": "application/xml",
            "Authorization": "Basic YWRtaW46c2VjcmV0MTIz",
            "X-Source": "datagen",
        },
        "_headersDesc": {
            "Content-Type": "XML内容类型",
            "Authorization": "Basic认证",
        },
        "authConfig": {
            "type": "basic",
            "username": "admin",
            "password": "secret123",
        },
        "bodyType": "raw-xml",
        "bodyView": "tree",
        "bodyTree": [
            {
                "name": "CreateOrderRequest",
                "label": "创建订单请求",
                "remark": None,
                "type": "object",
                "required": True,
                "defaultValue": None,
                "optionsSource": None,
                "validation": None,
                "batchEnabled": False,
                "children": [
                    {
                        "name": "tenantId",
                        "label": "租户ID",
                        "remark": None,
                        "type": "string",
                        "required": True,
                        "defaultValue": "T10001",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                    {
                        "name": "orderNo",
                        "label": "订单号",
                        "remark": None,
                        "type": "string",
                        "required": True,
                        "defaultValue": "ORD-20260607-001",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                    {
                        "name": "amount",
                        "label": "订单金额",
                        "remark": None,
                        "type": "number",
                        "required": True,
                        "defaultValue": "199.90",
                        "optionsSource": None,
                        "validation": None,
                        "batchEnabled": False,
                    },
                ],
            }
        ],
        "rawBody": '<?xml version="1.0" encoding="UTF-8"?>\n<CreateOrderRequest>\n  <tenantId>T10001</tenantId>\n  <orderNo>ORD-20260607-001</orderNo>\n  <amount>199.90</amount>\n</CreateOrderRequest>',
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_post_raw_xml_basic"),
    )
    print("Updated http_post_raw_xml_basic")

    # ============================================================
    # 6. http_post_raw_text_apikey_header
    # POST /api/v1/messages/text — Raw Text + API Key Header 提交文本消息
    # ============================================================
    rm = {
        "query": {
            "channel": "sms",
        },
        "_queryDesc": {
            "channel": "消息渠道",
        },
        "headers": {
            "Content-Type": "text/plain",
            "Accept": "text/plain",
            "X-Api-Key": "mock-api-key-xyz789",
            "X-Tenant-Id": "T10001",
        },
        "_headersDesc": {
            "X-Api-Key": "Header认证Key",
            "X-Tenant-Id": "租户ID",
        },
        "authConfig": {
            "type": "apikey",
            "key": "X-Api-Key",
            "value": "mock-api-key-xyz789",
            "addTo": "header",
        },
        "bodyType": "raw-text",
        "rawBody": "您好，张三，您的验证码是 123456，5分钟内有效。",
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_post_raw_text_apikey_header"),
    )
    print("Updated http_post_raw_text_apikey_header")

    # ============================================================
    # 7. http_post_form_data
    # POST /api/v1/files/upload — Form Data 上传文件
    # ============================================================
    rm = {
        "query": {
            "folder": "reports",
        },
        "_queryDesc": {
            "folder": "上传目录",
        },
        "headers": {
            "Accept": "application/json",
            "Authorization": "Bearer mock-access-token-abc123",
        },
        "_headersDesc": {
            "Authorization": "Bearer认证令牌",
        },
        "authConfig": {
            "type": "bearer",
            "token": "mock-access-token-abc123",
        },
        "bodyType": "form-data",
        "formData": [
            {
                "key": "file",
                "value": "/tmp/test-upload.txt",
                "description": "待上传文件路径或文件内容",
                "enabled": True,
            },
            {
                "key": "bizType",
                "value": "USER_AVATAR",
                "description": "业务类型",
                "enabled": True,
            },
            {
                "key": "overwrite",
                "value": "false",
                "description": "是否覆盖同名文件",
                "enabled": True,
            },
        ],
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_post_form_data"),
    )
    print("Updated http_post_form_data")

    # ============================================================
    # 8. http_post_urlencoded
    # POST /oauth/token — x-www-form-urlencoded + Basic Auth 登录获取Token
    # ============================================================
    rm = {
        "query": {},
        "headers": {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": "Basic Y2xpZW50LWFwcDpzZWNyZXQ0NTY=",
        },
        "_headersDesc": {
            "Content-Type": "表单编码类型",
            "Authorization": "客户端Basic认证",
        },
        "authConfig": {
            "type": "basic",
            "username": "client-app",
            "password": "secret456",
        },
        "bodyType": "x-www-form-urlencoded",
        "urlEncodedData": {
            "grant_type": "password",
            "username": "testuser",
            "password": "testpass123",
            "scope": "profile roles",
        },
        "_urlEncodedDesc": {
            "grant_type": "授权模式",
            "username": "登录用户名",
            "password": "登录密码",
            "scope": "权限范围",
        },
    }
    cur.execute(
        "UPDATE df_http_source SET request_mapping_json = ? WHERE source_code = ?",
        (json.dumps(rm, ensure_ascii=False), "http_post_urlencoded"),
    )
    print("Updated http_post_urlencoded")

    conn.commit()

    # ============================================================
    # 验证：检查是否还有 ${} 变量残留
    # ============================================================
    print("\n=== 验证：检查 ${} 变量残留 ===")
    cur.execute("SELECT source_code, path, request_mapping_json FROM df_http_source")
    issues = []
    for row in cur.fetchall():
        source_code, path, rm_json = row
        # 检查 path
        if "${" in path:
            issues.append(f"  {source_code}.path 仍有变量: {path}")
        # 检查 request_mapping_json
        if rm_json and "${" in rm_json:
            # 找出具体哪些字段还有变量
            obj = json.loads(rm_json)
            _find_vars(obj, source_code, issues)

    if issues:
        print("发现残留变量:")
        for issue in issues:
            print(issue)
    else:
        print("所有 ${} 变量已替换完毕，无残留。")

    conn.close()
    print("\n完成！")


def _find_vars(obj, source_code, issues, prefix=""):
    """递归查找 JSON 对象中的 ${} 变量。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            _find_vars(v, source_code, issues, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _find_vars(v, source_code, issues, f"{prefix}[{i}]")
    elif isinstance(obj, str) and "${" in obj:
        issues.append(f"  {source_code}{prefix}: {obj}")


if __name__ == "__main__":
    main()
