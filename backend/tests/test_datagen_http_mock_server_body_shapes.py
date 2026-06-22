"""Datagen HTTP mock server 的请求体形态测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_harness = str(Path(__file__).resolve().parents[1] / "packages" / "harness")
if _harness not in sys.path:
    sys.path.insert(0, _harness)

from scripts.datagen_http_mock_server import create_app


def test_create_user_requires_nested_json_body() -> None:
    client = TestClient(create_app())

    bad = client.post("/api/v1/users", json={"tenantId": "T10001"})
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/users",
        json={
            "tenantId": "T10001",
            "user": {
                "name": "张三",
                "age": 28,
                "enabled": True,
                "profile": {"email": "zhangsan@example.com"},
            },
            "tags": ["mock"],
        },
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["profile"]["email"] == "zhangsan@example.com"


def test_oauth_token_requires_urlencoded_form_fields() -> None:
    client = TestClient(create_app())

    bad = client.post("/oauth/token", data={"username": "demo"})
    assert bad.status_code == 400

    ok = client.post(
        "/oauth/token",
        data={
            "grant_type": "password",
            "username": "demo",
            "password": "secret",
            "scope": "orders:write",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["scope"] == "orders:write"


def test_upload_file_requires_form_data_fields() -> None:
    client = TestClient(create_app())

    bad = client.post("/api/v1/files/upload", files={"file": ("demo.txt", b"abc", "text/plain")})
    assert bad.status_code == 400

    ok = client.post(
        "/api/v1/files/upload?folder=orders",
        files={
            "file": ("demo.txt", b"abc", "text/plain"),
            "bizType": (None, "ORDER"),
        },
        headers={"Authorization": "Bearer token"},
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["bizType"] == "ORDER"


def test_create_order_with_items_uses_nested_json() -> None:
    client = TestClient(create_app())

    ok = client.post(
        "/api/v1/orders/with-items",
        json={
            "buyer_id": "U10001",
            "items": [
                {
                    "product_id": "SKU10001",
                    "sku_id": "SKU10001",
                    "quantity": 2,
                    "unit_price": 299,
                }
            ],
            "delivery": {"city": "上海", "address": "浦东新区"},
        },
    )
    assert ok.status_code == 200
    payload = ok.json()["data"]
    assert payload["items"][0]["sku_id"] == "SKU10001"
    assert payload["delivery"]["city"] == "上海"
