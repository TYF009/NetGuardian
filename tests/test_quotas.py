"""Completed jobs still consume admission rate budget; scheduling shares it."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from probe_core.policy import CloudPolicy
from service.api import create_app
from service.database import Job, Monitor
from service.monitoring import tick
from service.schema import upgrade
from service.settings import Settings


def test_completed_jobs_and_scheduler_share_rate_budget(tmp_path):
    policy = CloudPolicy("v1", frozenset({("example.com", 443, "https")}))
    settings = Settings(
        f"sqlite:///{tmp_path / 'quota.db'}",
        {"a" * 32: "one", "b" * 32: "two"},
        {"one": policy, "two": policy},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    one = {"Authorization": "Bearer " + "a" * 32}
    two = {"Authorization": "Bearer " + "b" * 32}
    body = {"target": "https://example.com", "kind": "http"}
    with app.state.sessions.begin() as session:
        for _ in range(60):
            session.add(
                Job(
                    workspace="one",
                    kind="http",
                    target=body["target"],
                    policy_version="v1",
                    state="succeeded",
                )
            )
        session.add(Monitor(workspace="one", name="Fixture", kind="http", target=body["target"]))
    response = client.post("/api/jobs", headers=one, json=body)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    assert client.post("/api/jobs", headers=two, json=body).status_code == 202
    tick(app.state.sessions, settings.policies)
    with app.state.sessions.begin() as session:
        assert len(session.scalars(select(Job).where(Job.workspace == "one")).all()) == 60
        session.execute(
            update(Job)
            .where(Job.workspace == "one")
            .values(created_at=datetime.now(UTC) - timedelta(seconds=61))
        )
    tick(app.state.sessions, settings.policies)
    with app.state.sessions() as session:
        assert len(session.scalars(select(Job).where(Job.workspace == "one")).all()) == 61
    assert client.post("/api/jobs", headers=one, json=body).status_code == 202
