from __future__ import annotations

from fastapi.testclient import TestClient

from app.gateway import config as gateway_config_module
from app.gateway.app import create_app


def _reset_gateway_config_cache() -> None:
    gateway_config_module._gateway_config = None


def test_gateway_allows_cors_preflight_for_nlp2sql(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    _reset_gateway_config_cache()

    client = TestClient(create_app())
    response = client.options(
        "/api/nlp2sql/data-sources",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_gateway_default_cors_origins_include_unified_proxy(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    _reset_gateway_config_cache()

    client = TestClient(create_app())
    response = client.options(
        "/api/nlp2sql/data-sources",
        headers={
            "Origin": "http://localhost:2026",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:2026"
    assert "POST" in response.headers["access-control-allow-methods"]
