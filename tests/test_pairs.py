"""Comparison jobs are authorized and queued atomically."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.api import create_app
from service.database import Agent, DiagnosticPair, Job
from service.schema import upgrade
from service.settings import Settings


def test_pair_authorization_and_two_slot_quota(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'pairs.db'}",
        {"a" * 32: "one", "b" * 32: "two"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    auth = {"Authorization": "Bearer " + "a" * 32}
    with app.state.sessions.begin() as session:
        agent = Agent(workspace="one", name="Fixture", credential_hash="a" * 64)
        other = Agent(workspace="two", name="Other", credential_hash="b" * 64)
        session.add_all([agent, other])
        session.flush()
        agent_id, other_id = agent.id, other.id
    body = {"target": "https://example.com", "kind": "http", "agent_id": agent_id}
    path = "/api/diagnostic-pairs"
    for invalid_id in (str(uuid4()), other_id):
        assert (
            client.post(path, headers=auth, json={**body, "agent_id": invalid_id}).status_code
            == 404
        )
    assert client.post(path, headers=auth, json={**body, "agent_id": None}).status_code == 422
    assert (
        client.post(path, headers=auth, json={**body, "target": "https://evil.test"}).status_code
        == 403
    )
    assert client.get("/api/jobs", headers=auth).json() == []
    response = client.post(path, headers=auth, json=body)
    assert response.status_code == 202
    pair = response.json()
    history = client.get(path, headers=auth).json()
    assert len(history) == 1 and history[0]["id"] == pair["id"]
    assert history[0]["cloud_job_id"] == pair["cloud_job_id"]
    assert history[0]["agent_job_id"] == pair["agent_job_id"]
    assert client.get(path, headers={"Authorization": "Bearer " + "b" * 32}).json() == []
    restarted = TestClient(create_app(settings))
    assert restarted.get(path, headers=auth).json() == history
    with app.state.sessions() as session:
        cloud = session.get(Job, pair["cloud_job_id"])
        local = session.get(Job, pair["agent_job_id"])
        assert cloud.agent_id is None and local.agent_id == agent_id
        assert cloud.target == local.target == body["target"]
        assert cloud.kind == local.kind == "http"
        assert cloud.created_at == local.created_at
        assert cloud.policy_version == local.policy_version
    for _ in range(17):
        assert (
            client.post(
                "/api/jobs", headers=auth, json={"kind": "http", "target": body["target"]}
            ).status_code
            == 202
        )
    assert client.post(path, headers=auth, json=body).status_code == 429
    with app.state.sessions() as session:
        assert len(session.scalars(select(Job)).all()) == 19
        assert len(session.scalars(select(DiagnosticPair)).all()) == 1

    # Paired evidence remains intact when generic job retention runs.
    from datetime import UTC, datetime, timedelta

    from service.retention import prune

    with app.state.sessions.begin() as session:
        for identifier in (pair["cloud_job_id"], pair["agent_job_id"]):
            job = session.get(Job, identifier)
            job.state = "succeeded"
            job.created_at = datetime.now(UTC) - timedelta(days=60)
    assert prune(app.state.sessions, "one", apply=True)["count"] == 0
    assert client.get(path, headers=auth).json() == history
