from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from xagent.core.datamakepool.orchestration import RunRuntimeBridge
from xagent.core.datamakepool.runs import RunService
from xagent.web.models import Base
from xagent.web.models.task import Task
from xagent.web.models.user import User


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_task_graph(session) -> tuple[User, Task]:
    user = User(username="trial_user", password_hash="hashed", is_admin=True)
    session.add(user)
    session.flush()

    task = Task(user_id=user.id, title="trial", description="trial task")
    session.add(task)
    session.commit()
    return user, task


def test_execute_trial_runs_http_mapping_end(db_session, monkeypatch):
    user, task = _seed_task_graph(db_session)
    technical_graph = {
        "nodes": [
            {"step_id": "start_1", "step_type": "start", "name": "start"},
            {
                "step_id": "http_1",
                "step_type": "http_step",
                "name": "fetch user",
                "depends_on": ["start_1"],
                "resolved_execution_plan": {
                    "asset_ref": "http_asset_1",
                    "method": "GET",
                    "url": "https://example.test/user",
                    "output_mapping": {
                        "user_name": "$response.json.user.name",
                        "user_id": "$response.json.user.id",
                    },
                },
            },
            {
                "step_id": "mapping_1",
                "step_type": "mapping",
                "name": "map user",
                "depends_on": ["http_1"],
                "resolved_execution_plan": {
                    "output_mapping": {
                        "greeting": "$steps.http_1.user_name",
                        "identifier": "$steps.http_1.user_id",
                    }
                },
            },
            {
                "step_id": "end_1",
                "step_type": "end",
                "name": "end",
                "depends_on": ["mapping_1"],
            },
        ]
    }

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"user":{"id":7,"name":"alice"}}'

        class _Elapsed:
            @staticmethod
            def total_seconds() -> float:
                return 0.012

        elapsed = _Elapsed()

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"user": {"id": 7, "name": "alice"}}

    monkeypatch.setattr(
        "xagent.core.datamakepool.executors.http.executor.requests.request",
        lambda *args, **kwargs: _FakeResponse(),
    )

    run_service = RunService(db=db_session, runtime_bridge=RunRuntimeBridge())
    created = run_service.create_run(
        entry_type="chat",
        initiator_user_id=user.id,
        task_id=task.id,
        technical_graph=technical_graph,
    )

    result = run_service.execute_trial(
        run_id=created["run_id"],
        technical_graph=technical_graph,
    )

    assert result["status"] == "succeeded"
    assert result["final_output"] == {"greeting": "alice", "identifier": 7}

    steps = run_service.get_run_steps(created["run_id"])
    assert [step["status"] for step in steps] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    assert steps[1]["resolved_execution_plan_snapshot"]["url"] == "https://example.test/user"
    assert steps[1]["output_snapshot"]["response_snapshot"]["status_code"] == 200


def test_execute_trial_runs_sql_step(db_session):
    user, task = _seed_task_graph(db_session)
    technical_graph = {
        "nodes": [
            {"step_id": "start_1", "step_type": "start", "name": "start"},
            {
                "step_id": "sql_1",
                "step_type": "sql_step",
                "name": "fetch answer",
                "depends_on": ["start_1"],
                "resolved_execution_plan": {
                    "asset_ref": "sql_asset_1",
                    "sql": "SELECT 42 AS answer",
                    "param_template": {},
                    "output_mapping": {"answer": "$response.first_row.answer"},
                },
            },
            {
                "step_id": "end_1",
                "step_type": "end",
                "name": "end",
                "depends_on": ["sql_1"],
            },
        ]
    }

    run_service = RunService(db=db_session, runtime_bridge=RunRuntimeBridge())
    created = run_service.create_run(
        entry_type="chat",
        initiator_user_id=user.id,
        task_id=task.id,
        technical_graph=technical_graph,
    )

    result = run_service.execute_trial(
        run_id=created["run_id"],
        technical_graph=technical_graph,
    )

    assert result["status"] == "succeeded"
    assert result["final_output"] == {"answer": 42}

    steps = run_service.get_run_steps(created["run_id"])
    assert steps[1]["status"] == "succeeded"
    assert steps[1]["output_snapshot"]["result_snapshot"]["rows"] == [{"answer": 42}]
