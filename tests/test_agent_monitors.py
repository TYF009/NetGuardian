"""Agent schedules remain tenant-scoped and fail closed on revocation."""

import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.api import create_app
from service.database import Agent, Incident, Job, Monitor
from service.monitoring import tick
from service.schema import upgrade
from service.settings import Settings
from service.worker import run_once


def test_agent_monitor_routing_and_revocation(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'agent-monitor.db'}",
        {"a" * 32: "one"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    auth = {"Authorization": "Bearer " + "a" * 32}
    with app.state.sessions.begin() as session:
        agent = Agent(workspace="one", name="Local", credential_hash="a" * 64)
        from service.database import Workspace

        session.add(Workspace(id="other"))
        foreign = Agent(workspace="other", name="Other", credential_hash="b" * 64)
        session.add_all([agent, foreign])
        session.flush()
        agent_id, foreign_id = agent.id, foreign.id
    body = {
        "name": "Local HTTP",
        "target": "https://example.com",
        "kind": "http",
        "agent_id": agent_id,
    }
    assert (
        client.post(
            "/api/monitors", headers=auth, json={**body, "agent_id": foreign_id}
        ).status_code
        == 404
    )
    response = client.post("/api/monitors", headers=auth, json=body)
    assert response.status_code == 201
    monitor_id = response.json()["id"]
    tick(app.state.sessions, settings.policies)
    tick(app.state.sessions, settings.policies)
    assert not asyncio.run(run_once(app.state.sessions, settings.policies, vantage_id=uuid4()))
    with app.state.sessions() as session:
        jobs = session.scalars(select(Job)).all()
        assert len(jobs) == 1 and jobs[0].agent_id == agent_id
        assert session.get(Monitor, monitor_id).agent_id == agent_id
    assert client.delete(f"/api/agents/{agent_id}", headers=auth).status_code == 204
    tick(app.state.sessions, settings.policies)
    with app.state.sessions() as session:
        assert session.get(Monitor, monitor_id).enabled == 0
        job = session.scalar(select(Job))
        assert job.state == "failed" and job.result is None
        assert session.scalars(select(Incident)).all() == []
    assert (
        client.patch(
            f"/api/monitors/{monitor_id}", headers=auth, json={"enabled": True}
        ).status_code
        == 409
    )
