"""GDP mock HTTP 种子数据的请求体配置测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_harness = str(Path(__file__).resolve().parents[1] / "packages" / "harness")
if _harness not in sys.path:
    sys.path.insert(0, _harness)

import pytest

from app.gdp.datagen.agent_catalog.models import AgentSceneSearchRequest
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from scripts.seed_gdp_mock_data import build_http_sources, build_scenes


def _source_by_code():
    return {source.sourceCode: source for source in build_http_sources()}


def test_post_sources_use_unified_body_fields_only() -> None:
    """POST 种子配置只允许使用前后端统一字段。"""

    allowed_keys = {
        "headers",
        "query",
        "authConfig",
        "bodyType",
        "rawBody",
        "bodyTree",
        "bodyView",
        "formData",
        "urlEncodedData",
    }

    for source in build_http_sources():
        if source.method.value != "POST":
            continue
        mapping = source.requestMapping
        assert "formFields" not in mapping
        assert "body" not in mapping
        assert mapping["bodyType"] != "form-urlencoded"
        assert set(mapping).issubset(allowed_keys), source.sourceCode


def test_seed_post_examples_cover_all_body_shapes() -> None:
    """种子数据覆盖 JSON、嵌套 JSON、urlencoded、multipart、XML、纯文本。"""

    sources = _source_by_code()

    assert sources["httpCreatePendingOrder"].requestMapping["bodyType"] == "raw-json"
    assert "metadata" in sources["httpCreatePendingOrder"].requestMapping["rawBody"]

    nested = sources["httpCreateOrderWithItems"].requestMapping
    assert nested["bodyType"] == "raw-json"
    assert "items" in nested["rawBody"]
    assert "delivery" in nested["rawBody"]
    assert nested["bodyTree"]

    assert sources["httpOAuthToken"].requestMapping["bodyType"] == "x-www-form-urlencoded"
    assert sources["httpOAuthToken"].requestMapping["urlEncodedData"]["username"] == "${input.username}"

    assert sources["httpUploadFile"].requestMapping["bodyType"] == "form-data"
    assert any(row["key"] == "file" for row in sources["httpUploadFile"].requestMapping["formData"])

    assert sources["httpCreateSoapOrder"].requestMapping["bodyType"] == "raw-xml"
    assert "<CreateOrderRequest>" in sources["httpCreateSoapOrder"].requestMapping["rawBody"]

    assert sources["httpSendTextMessage"].requestMapping["bodyType"] == "raw-text"
    assert sources["httpSendTextMessage"].requestMapping["rawBody"] == "${input.messageText}"


def test_seed_includes_http_sql_multi_step_scene() -> None:
    """主种子数据必须包含 HTTP 与 SQL 串联的多步骤场景。"""

    scenes = {scene.sceneCode: scene for scene in build_scenes()}
    scene = scenes["mvp4a_order_payment_inventory_sql_flow"]

    assert len(scene.steps) == 5
    assert [step.stepId for step in scene.steps] == [
        "create_order",
        "lock_inventory",
        "create_payment",
        "query_payment",
        "check_member_orders",
    ]
    assert {step.type.value for step in scene.steps} == {"HTTP", "SQL"}
    assert scene.steps[1].dependsOn == ["create_order"]
    assert scene.steps[4].dependsOn == ["query_payment"]
    assert scene.resultMapping["pay_status"] == "${steps.query_payment.outputs.pay_status}"
    assert scene.resultMapping["history_order_no"] == "${steps.check_member_orders.outputs.history_order_no}"

    for step in scene.steps:
        if step.type.value != "HTTP" or step.method.value != "POST":
            continue
        assert "formFields" not in step.requestMapping
        assert "body" not in step.requestMapping
        assert step.requestMapping["bodyType"] == "raw-json"


def test_seed_includes_mvp3_runtime_planstep_scenes() -> None:
    """MVP3 Runtime 验收必须有三个独立 Scene，而不是一个复合 Scene。"""

    scenes = {scene.sceneCode: scene for scene in build_scenes()}

    create_scene = scenes["create_order"]
    pay_scene = scenes["pay_order"]
    query_scene = scenes["query_order"]

    assert len(create_scene.steps) == 1
    assert create_scene.steps[0].path == "/api/v1/orders/create"
    assert create_scene.resultMapping["order_id"] == "${steps.create_order_http.outputs.order_id}"
    assert "pay_status" not in create_scene.resultMapping

    assert len(pay_scene.steps) == 1
    assert pay_scene.steps[0].path == "/api/v1/payments/pay"
    assert pay_scene.inputSchema[0].name == "order_id"
    assert pay_scene.inputSchema[0].semanticType == "ORDER_ID"
    assert pay_scene.resultMapping["pay_status"] == "${steps.pay_order_http.outputs.pay_status}"

    assert len(query_scene.steps) == 1
    assert query_scene.steps[0].path == "/api/v1/orders/${input.order_id}/status"
    assert query_scene.sideEffects == []
    assert query_scene.resultMapping["pay_status"] == "${steps.query_order_http.outputs.pay_status}"


@pytest.mark.anyio
async def test_mvp3_runtime_planstep_scenes_are_catalog_search_top_hits() -> None:
    """真实 seed 场景应能被 Runtime 每个 PlanStep 的目标检索到。"""

    service = AgentCatalogService(_FakeSceneRepository(build_scenes()))

    create_result = await service.search_scene_contracts(
        AgentSceneSearchRequest(goal="创建订单", envCode="dev", userInputs={"buyer_id": "U10001"}),
    )
    pay_result = await service.search_scene_contracts(
        AgentSceneSearchRequest(goal="支付订单", envCode="dev", userInputs={"order_id": "ORD-MVP3-00001"}),
    )
    query_result = await service.search_scene_contracts(
        AgentSceneSearchRequest(goal="查询订单状态", envCode="dev", userInputs={"order_id": "ORD-MVP3-00001"}),
    )

    assert create_result.candidates[0].contract.sceneCode == "create_order"
    assert pay_result.candidates[0].contract.sceneCode == "pay_order"
    assert query_result.candidates[0].contract.sceneCode == "query_order"


class _FakeSceneRepository:
    def __init__(self, scenes):
        self._scenes = {scene.sceneCode: scene for scene in scenes}

    async def list_scenes(self, **_kwargs):
        return [SimpleNamespace(sceneCode=scene.sceneCode) for scene in self._scenes.values()]

    async def get_published_scene(self, scene_code: str):
        return SimpleNamespace(sceneCode=scene_code, versionNo=1, definition=self._scenes[scene_code])
