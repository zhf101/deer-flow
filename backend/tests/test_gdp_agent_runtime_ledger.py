"""GDP Agent Runtime 账本 seam 一致性测试。"""

from __future__ import annotations

import pytest

from app.gdp.agent_runtime.flow import create_single_step, create_task_run, make_scene_action
from app.gdp.agent_runtime.ledger.memory import MemoryLedger
from app.gdp.agent_runtime.ledger.sql import SqlLedger
from app.gdp.agent_runtime.repository import AgentRuntimeRepository
from app.gdp.agent_runtime.store import Store
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


def test_ledger_compatibility_exports_point_to_new_adapters() -> None:
    """旧导入路径必须继续指向新的 ledger adapter，避免调用方一次性迁移。"""

    assert Store is MemoryLedger
    assert AgentRuntimeRepository is SqlLedger


@pytest.mark.anyio
async def test_sql_ledger_hydrates_same_snapshot_as_memory_ledger(tmp_path) -> None:
    """SQL 账本恢复后的内存快照应与持久化前保持一致。"""

    db_path = tmp_path / "agent-runtime-ledger.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None

        memory = MemoryLedger()
        task_run = create_task_run("造一笔已支付订单", env_code="SIT1")
        step = create_single_step(task_run)
        action = make_scene_action(step, "create_paid_order", {"buyer_id": "U1"})
        memory.save_task_run(task_run)
        memory.save_step(step)
        memory.save_action(action)
        memory.save_payload(task_run.task_run_id, action.input_ref, {"buyer_id": "U1"})

        before_snapshot = memory.export_task_run(task_run.task_run_id)
        before_timeline = memory.get_timeline(task_run.task_run_id)

        sql_ledger = SqlLedger(session_factory)
        await sql_ledger.persist_store(memory, task_run.task_run_id)
        restored = await sql_ledger.hydrate_store(task_run.task_run_id)

        assert restored.export_task_run(task_run.task_run_id) == before_snapshot
        assert restored.get_timeline(task_run.task_run_id) == before_timeline
    finally:
        await close_engine()
