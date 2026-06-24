"""GDP Agent Runtime ContextItem 复用测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.gdp.agent_runtime import api as runtime_api
from app.gdp.agent_runtime import runner as runtime_runner
from app.gdp.agent_runtime.domain.context import ContextItem
from app.gdp.agent_runtime.domain.factories import create_task_run
from app.gdp.agent_runtime.store import Store
from app.gdp.agent_runtime.support.errors import RuntimeConflictError
from app.gdp.agent_runtime.workflows.context_items import filter_reusable_context_items, import_context_items


class _ContextCatalog:
    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ):
        from _agent_runtime_catalog_fakes import make_candidate

        if "创建订单" in goal:
            scene_code = "create_order"
        elif "支付" in goal:
            scene_code = "pay_order"
        else:
            scene_code = "query_order"
        return ([make_candidate(scene_code, scene_name=goal)], [goal])

    async def get_contract(self, *, scene_code: str, user_inputs: dict[str, Any]):
        from _agent_runtime_catalog_fakes import make_candidate

        return make_candidate(scene_code)


def _make_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(runtime_api, "_store", Store())
    monkeypatch.setattr(runtime_runner, "get_catalog", lambda: _ContextCatalog())
    app = FastAPI()
    app.include_router(runtime_api.router, prefix="/api/v1/datagen")
    return app


@pytest.mark.anyio
async def test_context_items_are_extracted_and_listed_without_value_ref(monkeypatch: pytest.MonkeyPatch):
    """完成任务会抽取可复用上下文，查询接口只返回安全预览。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict[str, Any]):
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-CONTEXT-1"}, "errors": []}
        if scene_code == "pay_order":
            return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}
        return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "创建订单并支付", "env_code": "SIT1", "thread_id": "thread-context"},
        )
        task_run_id = create.json()["task_run_id"]
        start = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{task_run_id}/start",
            json={"inputs": {"buyer_id": "U1"}},
        )
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "COMPLETED"

        listed = await client.get(
            "/api/v1/datagen/agent-runtime/context-items",
            params={"threadId": "thread-context", "envCode": "SIT1", "semanticType": "ORDER_ID"},
        )

    assert listed.status_code == 200, listed.text
    items = listed.json()
    assert len(items) == 1
    assert items[0]["source_task_run_id"] == task_run_id
    assert items[0]["name"] == "order_id"
    assert items[0]["semantic_type"] == "ORDER_ID"
    assert items[0]["value_preview"] == "ORDER-CONTEXT-1"
    assert "value_ref" not in items[0]


@pytest.mark.anyio
async def test_start_imports_selected_context_item_as_context_variable(monkeypatch: pytest.MonkeyPatch):
    """新任务显式选择 ContextItem 后，步骤绑定可把它作为 CONTEXT 变量消费。"""

    received_pay_inputs: list[dict[str, Any]] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict[str, Any]):
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-CONTEXT-2"}, "errors": []}
        if scene_code == "pay_order":
            received_pay_inputs.append(dict(inputs))
            return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}
        return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_source = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "创建订单并支付", "env_code": "SIT1", "thread_id": "thread-context"},
        )
        source_task_run_id = create_source.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{source_task_run_id}/start",
            json={"inputs": {"buyer_id": "U2"}},
        )
        contexts = await client.get(
            "/api/v1/datagen/agent-runtime/context-items",
            params={"threadId": "thread-context", "envCode": "SIT1", "semanticType": "ORDER_ID"},
        )
        context_item_id = contexts.json()[0]["context_item_id"]

        create_target = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "支付已有订单并查询状态", "env_code": "SIT1", "thread_id": "thread-context"},
        )
        target_task_run_id = create_target.json()["task_run_id"]
        start_target = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{target_task_run_id}/start",
            json={"inputs": {}, "context_item_ids": [context_item_id]},
        )
        timeline = await client.get(f"/api/v1/datagen/agent-runtime/task-runs/{target_task_run_id}/timeline")

    assert start_target.status_code == 200, start_target.text
    assert start_target.json()["status"] == "COMPLETED"
    assert received_pay_inputs[1]["order_id"] == "ORDER-CONTEXT-2"
    context_variables = [
        item
        for item in timeline.json()["variables"]
        if item["name"] == "order_id" and item["provenance"]["source_type"] == "CONTEXT"
    ]
    assert len(context_variables) == 1
    assert context_variables[0]["provenance"]["source_id"] == context_item_id
    assert "value_ref" not in context_variables[0]


@pytest.mark.anyio
async def test_start_rejects_env_mismatched_context_item(monkeypatch: pytest.MonkeyPatch):
    """环境不匹配的 ContextItem 不能被导入到新任务。"""

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict[str, Any]):
        if scene_code == "create_order":
            return {"status": "SUCCESS", "finalOutput": {"order_id": "ORDER-CONTEXT-3"}, "errors": []}
        if scene_code == "pay_order":
            return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}
        return {"status": "SUCCESS", "finalOutput": {"pay_status": "PAID"}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    app = _make_app(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_source = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "创建订单并支付", "env_code": "SIT1", "thread_id": "thread-context"},
        )
        source_task_run_id = create_source.json()["task_run_id"]
        await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{source_task_run_id}/start",
            json={"inputs": {"buyer_id": "U3"}},
        )
        contexts = await client.get(
            "/api/v1/datagen/agent-runtime/context-items",
            params={"threadId": "thread-context", "envCode": "SIT1", "semanticType": "ORDER_ID"},
        )
        context_item_id = contexts.json()[0]["context_item_id"]

        create_target = await client.post(
            "/api/v1/datagen/agent-runtime/task-runs",
            json={"user_goal": "支付已有订单并查询状态", "env_code": "SIT2", "thread_id": "thread-context"},
        )
        target_task_run_id = create_target.json()["task_run_id"]
        start_target = await client.post(
            f"/api/v1/datagen/agent-runtime/task-runs/{target_task_run_id}/start",
            json={"inputs": {}, "context_item_ids": [context_item_id]},
        )

    assert start_target.status_code == 409


def test_context_item_filter_and_import_reject_unsafe_items():
    """污染、过期、不可复用的上下文项不能被查询或导入。"""

    now = datetime.now(UTC)
    source = create_task_run("来源任务", env_code="SIT1", user_id="u1", thread_id="thread-context")
    target = create_task_run("目标任务", env_code="SIT1", user_id="u1", thread_id="thread-context")
    store = Store()
    store.save_task_run(source)
    store.save_task_run(target)

    safe = ContextItem(
        context_item_id="ctx-safe",
        source_task_run_id=source.task_run_id,
        source_variable_id="var-safe",
        thread_id=source.thread_id,
        user_id=source.user_id,
        env_code=source.env_code,
        name="order_id",
        semantic_type="ORDER_ID",
        value_ref="ref:vars/var-safe",
        value_preview="ORDER-SAFE",
        sensitive=False,
        tainted=False,
        reusable=True,
        expires_at=None,
        created_at=now,
    )
    unsafe_items = [
        safe.model_copy(update={"context_item_id": "ctx-tainted", "tainted": True}),
        safe.model_copy(update={"context_item_id": "ctx-expired", "expires_at": now - timedelta(seconds=1)}),
        safe.model_copy(update={"context_item_id": "ctx-non-reusable", "reusable": False}),
    ]
    for item in [safe, *unsafe_items]:
        store.save_context_item(item)
    store.save_payload(source.task_run_id, safe.value_ref, "ORDER-SAFE")

    filtered = filter_reusable_context_items(
        store.list_context_items(thread_id="thread-context"),
        user_id="u1",
        thread_id="thread-context",
        env_code="SIT1",
        semantic_type="ORDER_ID",
        now=now,
    )

    assert [item.context_item_id for item in filtered] == ["ctx-safe"]
    imported = import_context_items(target, ["ctx-safe"], store)
    assert imported[0].provenance.source_type == "CONTEXT"
    assert store.get_payload(target.task_run_id, imported[0].value_ref) == "ORDER-SAFE"
    for item in unsafe_items:
        with pytest.raises(RuntimeConflictError, match="ContextItem"):
            import_context_items(target, [item.context_item_id], store)
