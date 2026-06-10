"""GDP Agent 记忆上下文注入测试。"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app.gdp.agent.nodes.intake import build_intake_node
from app.gdp.datagen.agent_memory.models import GDPAgentMemoryFactCreateRequest, GDPAgentMemoryFactIdRequest
from app.gdp.datagen.agent_memory.repository import GDPAgentMemoryRepository
from app.gdp.datagen.agent_memory.service import GDPAgentMemoryService
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


@pytest.fixture
async def memory_context_services(tmp_path):
    db_path = tmp_path / "gdp-agent-memory-context.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        memory_service = GDPAgentMemoryService(GDPAgentMemoryRepository(session_factory))
        task_service = DatagenTaskService(DatagenTaskRepository(session_factory))
        yield task_service, memory_service
    finally:
        await close_engine()


@pytest.mark.anyio
async def test_intake_injects_user_memory_context_without_changing_task_fact(memory_context_services):
    task_service, memory_service = memory_context_services
    fact = await memory_service.create_fact(
        GDPAgentMemoryFactCreateRequest(
            userId="user_1",
            scopeType="USER",
            scopeKey="user_1",
            category="system_alias",
            memoryKey="trade-system-alias",
            value={"sysCode": "TRADE", "aliases": ["交易", "订单"]},
            confidence=0.92,
            evidenceSummary="用户常把交易系统叫作订单系统。",
        )
    )
    intake = build_intake_node(task_service, memory_service)

    result = await intake(
        {"messages": [HumanMessage(content="帮我造一笔交易订单")], "env_code": "DEV"},
        {"configurable": {"thread_id": "thread-memory", "user_id": "user_1"}},
    )

    assert result["memory_context"]["enabled"] is True
    assert result["memory_context"]["userId"] == "user_1"
    assert result["memory_context"]["facts"][0]["factId"] == fact.factId
    assert result["memory_context"]["categories"]["system_alias"][0]["value"]["sysCode"] == "TRADE"
    assert result["memory_trace"][0]["factId"] == fact.factId
    task = await task_service.get_task_run(result["task_run_id"])
    assert task.normalizedGoal["rawIntent"] == "帮我造一笔交易订单"
    assert "memory_context" not in task.normalizedGoal
    used = await memory_service.list_facts(user_id="user_1")
    assert used[0].useCount == 1


@pytest.mark.anyio
async def test_intake_ignores_disabled_memory_context(memory_context_services):
    task_service, memory_service = memory_context_services
    fact = await memory_service.create_fact(
        GDPAgentMemoryFactCreateRequest(
            userId="user_1",
            scopeType="USER",
            scopeKey="user_1",
            category="environment_preference",
            memoryKey="prefer-test-env",
            value={"envCode": "TEST"},
            confidence=0.8,
        )
    )
    await memory_service.disable_fact(GDPAgentMemoryFactIdRequest(factId=fact.factId))
    intake = build_intake_node(task_service, memory_service)

    result = await intake(
        {"messages": [HumanMessage(content="帮我造一笔订单")]},
        {"configurable": {"thread_id": "thread-memory-disabled", "user_id": "user_1"}},
    )

    assert result["memory_context"]["enabled"] is True
    assert result["memory_context"]["facts"] == []
    assert result["memory_trace"] == []
