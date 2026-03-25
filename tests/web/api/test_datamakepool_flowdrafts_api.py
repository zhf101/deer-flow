from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from xagent.web.api.datamakepool.flowdrafts import router as flowdrafts_router
from xagent.web.auth_dependencies import get_current_user
from xagent.web.models import Base
from xagent.web.models.database import get_db
from xagent.web.models.dm_flow_draft import DMFlowDraft
from xagent.web.models.task import Task
from xagent.web.models.user import User


def test_trial_endpoint_rejects_non_runnable_preflight():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    user = User(username="api_user", password_hash="hashed", is_admin=True)
    session.add(user)
    session.flush()
    task = Task(user_id=user.id, title="task", description="task")
    session.add(task)
    session.flush()
    flowdraft = DMFlowDraft(
        task_id=task.id,
        status="draft",
        title="bad draft",
        objective="blocked trial",
        business_graph_payload={},
        technical_graph_payload={
            "nodes": [
                {
                    "step_id": "http_1",
                    "step_type": "http_step",
                    "name": "missing plan",
                    "depends_on": [],
                }
            ]
        },
        pending_issues_payload=[],
        created_by=user.id,
    )
    session.add(flowdraft)
    session.commit()

    app = FastAPI()
    app.include_router(flowdrafts_router)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    response = client.post(
        f"/api/datamakepool/flowdrafts/{flowdraft.id}/trial",
        json={"entry_type": "chat"},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["message"] == "FlowDraft preflight blocked trial execution"
    assert detail["preflight"]["is_runnable"] is False

    session.close()
    Base.metadata.drop_all(bind=engine)
