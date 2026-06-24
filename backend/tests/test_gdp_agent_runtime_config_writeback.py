"""GDP Agent Runtime MVP4-B 配置写回测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from _agent_runtime_catalog_fakes import FakeSceneCatalog, make_infra_candidate, make_source_candidate

from app.gdp.agent_runtime.adapters.catalog import AgentCatalogAdapter
from app.gdp.agent_runtime.adapters.config_writeback import DatagenConfigWritebackAdapter
from app.gdp.agent_runtime.flow import create_task_run
from app.gdp.agent_runtime.models import ProposalStatus, Requirement, RequirementLayer, RequirementProposal, RequirementStatus, TaskRunStatus
from app.gdp.agent_runtime.runner import run_task
from app.gdp.agent_runtime.store import Store
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.base.models import EnvironmentConfig, ServiceEndpointConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.base.service import BaseConfigService
from app.gdp.datagen.config.common.models import CapabilityType, ConfigStatus, HttpMethod, SqlOperation
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig, HttpSourceResponse
from app.gdp.datagen.config.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.factory import build_scene_service
from app.gdp.datagen.config.scene.models import SceneDefinition
from app.gdp.datagen.config.scene.repository import SceneRepository
from app.gdp.datagen.config.sqlsource.models import SqlSourceResponse
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def writeback_services(tmp_path):
    """真实 SQLite datagen service 依赖，用于配置写回集成测试。"""
    db_path = tmp_path / "runtime-writeback.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        base_repo = BaseConfigRepository(session_factory)
        scene_repo = SceneRepository(session_factory)
        yield {
            "base": BaseConfigService(base_repo),
            "base_repo": base_repo,
            "http": HttpSourceService(HttpSourceRepository(session_factory), base_repo),
            "sql_repo": SqlSourceRepository(session_factory),
            "scene": build_scene_service(session_factory),
            "scene_repo": scene_repo,
        }
    finally:
        await close_engine()


class FakeConfigWriteback:
    """测试用配置写回端口，记录调用并返回已发布 Scene。"""

    def __init__(self, scene_code: str) -> None:
        self.scene_code = scene_code
        self.calls: list[dict[str, Any]] = []

    async def create_and_publish_scene_from_sources(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="SUCCESS",
            target_kind="SCENE",
            target_code=self.scene_code,
            message=f"已自动创建并发布 Scene：{self.scene_code}",
            reason=None,
            validation_issues=[],
            parent_requirement_id=kwargs["scene_requirement"].requirement_id,
            source_requirement_id=kwargs["source_requirement"].requirement_id,
            proposal_id=kwargs["proposal"].proposal_id,
        )


class FailingConfigWriteback:
    """测试用失败写回端口。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_and_publish_scene_from_sources(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="FAILED",
            target_kind="SCENE",
            target_code=None,
            message="自动发布 Scene 失败。",
            reason="SceneDefinition 发布校验失败。",
            validation_issues=["steps[0].path: HTTP 步骤必须配置请求路径。"],
            parent_requirement_id=kwargs["scene_requirement"].requirement_id,
            source_requirement_id=kwargs["source_requirement"].requirement_id,
            proposal_id=kwargs["proposal"].proposal_id,
        )


class RaisingConfigWriteback:
    """若 workflow 错误调用写回端口则让测试失败。"""

    async def create_and_publish_scene_from_sources(self, **kwargs: Any) -> SimpleNamespace:
        raise AssertionError("Infra 未满足时不应调用配置写回端口")


class FakeSceneService:
    """记录 adapter 创建和发布的 Scene。"""

    def __init__(self) -> None:
        self.created: list[SceneDefinition] = []
        self.published: list[str] = []

    async def create_scene(self, scene: SceneDefinition, *, operator: str | None = None) -> SimpleNamespace:
        self.created.append(scene)
        return SimpleNamespace(definition=scene)

    async def publish_scene(self, scene_code: str, *, operator: str | None = None) -> SimpleNamespace:
        self.published.append(scene_code)
        return SimpleNamespace(sceneCode=scene_code)


class FakeHttpSourceService:
    async def get_http_source(self, source_code: str) -> HttpSourceResponse:
        return HttpSourceResponse(
            id="http-1",
            sourceCode=source_code,
            sourceName="创建订单接口",
            tags=["订单"],
            sysCode="TRADE",
            path="/api/orders",
            method=HttpMethod.POST,
            outputMapping={"order_id": "${RES_BODY(orderId)}"},
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
        )


class FakeSqlSourceService:
    async def get_sql_source(self, source_code: str) -> SqlSourceResponse:
        return SqlSourceResponse(
            id="sql-1",
            sourceCode=source_code,
            sourceName="查询订单 SQL",
            tags=["订单"],
            sysCode="TRADE",
            datasourceCode="orderDb",
            operation=SqlOperation.SELECT,
            sqlText="select id from orders where buyer_id = :buyer_id",
            normalizedSql="select id from orders where buyer_id = :buyer_id",
            createdAt=datetime.now(UTC),
            updatedAt=datetime.now(UTC),
        )


@pytest.mark.anyio
async def test_source_and_ready_infra_writeback_publishes_scene_then_executes(monkeypatch: pytest.MonkeyPatch):
    """Source 候选和 Infra ready 时，自动发布 Scene 并回弹父 SCENE 缺口继续执行。"""
    executed_scene_codes: list[str] = []

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        executed_scene_codes.append(scene_code)
        return {
            "status": "SUCCESS",
            "finalOutput": {"order_id": "ORDER-1", "pay_status": "PAID"},
            "errors": [],
        }

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)
    writeback = FakeConfigWriteback("auto_scene_create_paid_order")

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[],
            source_candidates=[
                make_source_candidate("createOrderApi", source_name="创建订单接口"),
                make_source_candidate("payOrderApi", source_name="支付订单接口", path="/api/payments"),
            ],
            infra_candidates=[
                make_infra_candidate(resource_type="HTTP", ready=True),
                make_infra_candidate(resource_type="HTTP", ready=True),
            ],
        ),
        config_writeback=writeback,
    )

    timeline = store.get_timeline(result.task_run_id)
    scene_requirement = next(item for item in timeline["requirements"] if item["layer"] == RequirementLayer.SCENE)
    writeback_decision = next(item for item in timeline["decisions"] if item["decision_kind"] == "CONFIG_WRITEBACK")

    assert result.status == TaskRunStatus.COMPLETED
    assert result.pending_question is None
    assert executed_scene_codes == ["auto_scene_create_paid_order"]
    assert len(writeback.calls) == 1
    assert writeback.calls[0]["source_candidates"][0].source_code == "createOrderApi"
    assert scene_requirement["status"] == "SATISFIED"
    assert scene_requirement["selected_scene_code"] == "auto_scene_create_paid_order"
    assert writeback_decision["status"] == "DECIDED"
    assert writeback_decision["target_type"] == "scene"
    assert writeback_decision["target_id"] == "auto_scene_create_paid_order"
    assert writeback_decision["input_ref"] is None
    assert "自动创建并发布 Scene" in writeback_decision["summary"]
    assert "WAITING_APPROVAL" not in str(timeline)


@pytest.mark.anyio
async def test_writeback_failure_waits_user_without_action_or_attempt(monkeypatch: pytest.MonkeyPatch):
    """自动发布 Scene 失败时保持等待用户，不创建执行动作。"""
    called = False

    async def fake_call_scene(scene_code: str, env_code: str, inputs: dict):
        nonlocal called
        called = True
        return {"status": "SUCCESS", "finalOutput": {}, "errors": []}

    monkeypatch.setattr("app.gdp.agent_runtime.adapters.scene.call_scene", fake_call_scene)
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)
    writeback = FailingConfigWriteback()

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[],
            source_candidates=[make_source_candidate("createOrderApi", source_name="创建订单接口")],
            infra_candidates=[make_infra_candidate(resource_type="HTTP", ready=True)],
        ),
        config_writeback=writeback,
    )

    timeline = store.get_timeline(result.task_run_id)
    writeback_decision = next(item for item in timeline["decisions"] if item["decision_kind"] == "CONFIG_WRITEBACK")
    assert called is False
    assert len(writeback.calls) == 1
    assert result.status == TaskRunStatus.WAITING_USER
    assert "自动发布组合 Scene 未完成" in (result.pending_question or "")
    assert "SceneDefinition 发布校验失败" in (result.pending_question or "")
    assert timeline["actions"] == []
    assert timeline["attempts"] == []
    assert writeback_decision["status"] == "FAILED"
    assert writeback_decision["target_id"] is None
    assert writeback_decision["input_ref"] is None


@pytest.mark.anyio
async def test_infra_missing_fields_skip_writeback_and_keep_discovery_tree():
    """Infra 有缺失字段时不写 Scene，仍展示 Source/Infra 缺口树。"""
    store = Store()
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    store.save_task_run(task_run)

    result = await run_task(
        task_run,
        SimpleNamespace(scene_code=None, inputs={"buyer_id": "U1"}),
        store,
        catalog=FakeSceneCatalog(
            candidates=[],
            source_candidates=[make_source_candidate("createOrderApi", source_name="创建订单接口")],
            infra_candidates=[make_infra_candidate(resource_type="HTTP", ready=False, missing_fields=["serviceEndpoint"])],
        ),
        config_writeback=RaisingConfigWriteback(),
    )

    timeline = store.get_timeline(result.task_run_id)
    assert result.status == TaskRunStatus.WAITING_USER
    assert "serviceEndpoint" in (result.pending_question or "")
    assert [item["layer"] for item in timeline["requirements"]] == [
        RequirementLayer.SCENE,
        RequirementLayer.SOURCE,
        RequirementLayer.INFRA,
    ]
    assert timeline["actions"] == []
    assert timeline["attempts"] == []
    assert not any(item["decision_kind"] == "CONFIG_WRITEBACK" for item in timeline["decisions"])


@pytest.mark.anyio
async def test_datagen_writeback_adapter_builds_published_scene_with_source_template_refs():
    """默认 adapter 通过 datagen service 发布带 Source 快照引用的组合 Scene。"""
    now = datetime.now(UTC)
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    scene_requirement = Requirement(
        requirement_id="req-scene",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SCENE,
        goal=task_run.user_goal,
        status=RequirementStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    source_requirement = Requirement(
        requirement_id="req-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SOURCE,
        goal=task_run.user_goal,
        status=RequirementStatus.RESOLVING,
        parent_requirement_id=scene_requirement.requirement_id,
        created_at=now,
        updated_at=now,
    )
    source_candidates = [
        make_source_candidate("createOrderApi", source_name="创建订单接口", requires_confirmation=False),
        make_source_candidate(
            "queryOrderSql",
            source_type="SQL",
            source_name="查询订单 SQL",
            datasource_code="orderDb",
            operation="SELECT",
            requires_confirmation=False,
        ),
    ]
    proposal = RequirementProposal(
        proposal_id="prop-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        requirement_id=source_requirement.requirement_id,
        source_candidates=source_candidates,
        status=ProposalStatus.PENDING,
        created_at=now,
    )
    scene_service = FakeSceneService()
    adapter = DatagenConfigWritebackAdapter(
        scene_service=scene_service,  # type: ignore[arg-type]
        http_source_service=FakeHttpSourceService(),  # type: ignore[arg-type]
        sql_source_service=FakeSqlSourceService(),  # type: ignore[arg-type]
    )

    result = await adapter.create_and_publish_scene_from_sources(
        task_run=task_run,
        scene_requirement=scene_requirement,
        source_requirement=source_requirement,
        proposal=proposal,
        source_candidates=source_candidates,
        infra_candidates=[
            make_infra_candidate(resource_type="HTTP", ready=True),
            make_infra_candidate(resource_type="SQL", ready=True),
        ],
        inputs={"buyer_id": "U1"},
    )

    scene = scene_service.created[0]
    assert result.status == "SUCCESS"
    assert scene_service.published == [scene.sceneCode]
    assert [step.templateRef.sourceCode for step in scene.steps if step.templateRef] == [
        "createOrderApi",
        "queryOrderSql",
    ]
    assert scene.steps[0].templateRef.type == "HTTP_SOURCE"
    assert scene.steps[1].templateRef.type == "SQL_SOURCE"


@pytest.mark.anyio
async def test_datagen_writeback_published_scene_can_be_read_by_agent_catalog(writeback_services):
    """真实 datagen 写入后，新发布 Scene 能被 Agent Catalog 读取契约。"""
    base: BaseConfigService = writeback_services["base"]
    http: HttpSourceService = writeback_services["http"]
    scene_repo: SceneRepository = writeback_services["scene_repo"]

    await base.upsert_system(SysConfig(sysCode="TRADE", sysName="交易系统", status=ConfigStatus.ENABLED))
    await base.upsert_environment(EnvironmentConfig(envCode="SIT1", envName="集成测试环境", status=ConfigStatus.ENABLED))
    await base.create_service_endpoint(
        ServiceEndpointConfig(
            envCode="SIT1",
            sysCode="TRADE",
            baseUrl="https://trade.example.test",
            status=ConfigStatus.ENABLED,
        )
    )
    await http.upsert_http_source(_order_http_source("createOrderApi"), operator="tester")

    now = datetime.now(UTC)
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    scene_requirement = Requirement(
        requirement_id="req-scene",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SCENE,
        goal=task_run.user_goal,
        status=RequirementStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    source_requirement = Requirement(
        requirement_id="req-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SOURCE,
        goal=task_run.user_goal,
        status=RequirementStatus.RESOLVING,
        parent_requirement_id=scene_requirement.requirement_id,
        created_at=now,
        updated_at=now,
    )
    source_candidates = [
        make_source_candidate(
            "createOrderApi",
            source_name="创建订单接口",
            sys_code="TRADE",
            requires_confirmation=True,
        )
    ]
    proposal = RequirementProposal(
        proposal_id="prop-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        requirement_id=source_requirement.requirement_id,
        source_candidates=source_candidates,
        status=ProposalStatus.PENDING,
        created_at=now,
    )
    adapter = DatagenConfigWritebackAdapter(
        scene_service=writeback_services["scene"],
        http_source_service=http,
        sql_source_service=FakeSqlSourceService(),  # type: ignore[arg-type]
    )

    result = await adapter.create_and_publish_scene_from_sources(
        task_run=task_run,
        scene_requirement=scene_requirement,
        source_requirement=source_requirement,
        proposal=proposal,
        source_candidates=source_candidates,
        infra_candidates=[make_infra_candidate(resource_type="HTTP", ready=True)],
        inputs={"buyerId": "U1"},
    )

    catalog = AgentCatalogAdapter(service=AgentCatalogService(scene_repo))
    candidate = await catalog.get_contract(scene_code=result.target_code, user_inputs={"buyerId": "U1"})
    published = await scene_repo.get_published_scene(result.target_code)

    assert result.status == "SUCCESS"
    assert candidate.scene_code == result.target_code
    assert candidate.requires_confirmation is True
    assert candidate.missing_inputs == []
    assert published.definition.steps[0].templateRef.sourceCode == "createOrderApi"


@pytest.mark.anyio
async def test_datagen_writeback_adapter_skips_when_infra_diagnostics_are_missing():
    """adapter 直连调用时，缺 Infra 诊断也不能写 Scene。"""
    now = datetime.now(UTC)
    task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
    scene_requirement = Requirement(
        requirement_id="req-scene",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SCENE,
        goal=task_run.user_goal,
        status=RequirementStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    source_requirement = Requirement(
        requirement_id="req-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        layer=RequirementLayer.SOURCE,
        goal=task_run.user_goal,
        status=RequirementStatus.RESOLVING,
        parent_requirement_id=scene_requirement.requirement_id,
        created_at=now,
        updated_at=now,
    )
    source_candidates = [make_source_candidate("createOrderApi", source_name="创建订单接口")]
    proposal = RequirementProposal(
        proposal_id="prop-source",
        task_run_id=task_run.task_run_id,
        step_id="step-1",
        requirement_id=source_requirement.requirement_id,
        source_candidates=source_candidates,
        status=ProposalStatus.PENDING,
        created_at=now,
    )
    scene_service = FakeSceneService()
    adapter = DatagenConfigWritebackAdapter(
        scene_service=scene_service,  # type: ignore[arg-type]
        http_source_service=FakeHttpSourceService(),  # type: ignore[arg-type]
        sql_source_service=FakeSqlSourceService(),  # type: ignore[arg-type]
    )

    result = await adapter.create_and_publish_scene_from_sources(
        task_run=task_run,
        scene_requirement=scene_requirement,
        source_requirement=source_requirement,
        proposal=proposal,
        source_candidates=source_candidates,
        infra_candidates=[],
        inputs={"buyer_id": "U1"},
    )

    assert result.status == "SKIPPED"
    assert "基础配置" in (result.reason or "")
    assert scene_service.created == []
    assert scene_service.published == []


def _order_http_source(source_code: str) -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode=source_code,
        sourceName="创建订单接口",
        tags=["订单", "支付"],
        capabilityType=CapabilityType.CREATE,
        businessDomain="交易",
        sideEffects=[
            {
                "effectType": "CREATE_ORDER",
                "target": "orders",
                "description": "创建一笔测试订单。",
            }
        ],
        agentDescription="创建一笔测试订单并返回订单号，适用于造已支付订单的前置步骤。",
        sysCode="TRADE",
        path="/api/orders",
        method=HttpMethod.POST,
        outputMapping={"orderId": "${RES_BODY(data.orderId)}"},
        outputMeta={"orderId": {"label": "订单号", "remark": "创建后的订单号。", "semanticType": "ORDER_ID"}},
        status=ConfigStatus.ENABLED,
    )
