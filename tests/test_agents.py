"""Agent credentials are scoped and enrollment tokens cannot be replayed."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from probe_core.contracts import Measurement, ProbeRequest, configuration_hash
from probe_core.policy import CloudPolicy
from service.api import create_app
from service.schema import upgrade
from service.settings import Settings


def test_enrollment_replay_assignment_upload_and_revocation(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'agents.db'}",
        {"a" * 32: "one"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    client = TestClient(create_app(settings))
    admin = {"Authorization": "Bearer " + "a" * 32}
    token = client.post("/api/agents/enrollment", headers=admin, json={"name": "Laptop"}).json()[
        "token"
    ]
    issued_events = client.get("/api/audit-events", headers=admin).json()
    assert len(issued_events) == 1
    assert issued_events[0]["action"] == "agent.enrollment_issued"
    assert UUID(issued_events[0]["resource_id"]).version == 4
    assert issued_events[0]["actor_kind"] == "workspace_operator"
    from service.agents import digest

    assert token not in str(issued_events)
    assert digest(token) not in str(issued_events)
    assert "Laptop" not in str(issued_events)
    response = client.post("/api/agent/enroll", json={"token": token})
    assert response.status_code == 201
    agent = response.json()
    auth = {"Authorization": "Bearer " + agent["credential"]}
    enrolled_events = client.get("/api/audit-events", headers=admin).json()
    assert enrolled_events[0]["action"] == "agent.enrolled"
    assert enrolled_events[0]["actor_kind"] == "enrollment_token_holder"
    assert token not in str(enrolled_events) and agent["credential"] not in str(enrolled_events)
    assert client.post("/api/agent/enroll", json={"token": token}).status_code == 401
    assert client.get("/api/jobs", headers=auth).status_code == 401
    job_id = client.post(
        "/api/jobs",
        headers=admin,
        json={"kind": "dns", "target": "https://example.com", "agent_id": agent["agent_id"]},
    ).json()["id"]
    assignment = client.post("/api/agent/poll", headers=auth).json()
    assert assignment["job"]["job_id"] == job_id
    assert client.post("/api/agent/poll", headers=auth).json()["job"] is None
    result = Measurement(
        job_id=UUID(job_id),
        attempt=assignment["attempt"],
        kind="dns",
        vantage_id=UUID(agent["agent_id"]),
        target="https://example.com",
        configuration_hash=configuration_hash(ProbeRequest.model_validate(assignment["job"])),
        observed_at="2026-11-04T00:00:00Z",
        probe_version="test",
        policy_version="v1",
        status="success",
    )
    upload = {
        "lease_token": assignment["lease_token"],
        "measurement": result.model_dump(mode="json"),
    }
    wrong = {**upload, "measurement": {**upload["measurement"], "configuration_hash": "0" * 64}}
    assert client.post("/api/agent/results", headers=auth, json=wrong).status_code == 422
    pending = client.get(f"/api/jobs/{job_id}", headers=admin).json()
    assert pending["state"] == "running"
    assert pending["result"] is None
    # A client-supplied receipt time must never become authoritative.
    upload["measurement"]["received_at"] = "2000-01-01T00:00:00Z"
    before = datetime.now(UTC)
    assert client.post("/api/agent/results", headers=auth, json=upload).status_code == 200
    saved = client.get(f"/api/jobs/{job_id}", headers=admin).json()["result"]
    receipt = datetime.fromisoformat(saved["received_at"].replace("Z", "+00:00"))
    assert before <= receipt <= datetime.now(UTC)
    assert saved["observed_at"] == upload["measurement"]["observed_at"]
    upload["measurement"]["received_at"] = None
    assert client.post("/api/agent/results", headers=auth, json=upload).json()["duplicate"] is True
    assert client.get(f"/api/jobs/{job_id}", headers=admin).json()["result"] == saved
    conflict = {**upload, "measurement": {**upload["measurement"], "probe_version": "changed"}}
    assert client.post("/api/agent/results", headers=auth, json=conflict).status_code == 409
    # Legacy records remain unknown, rather than receiving a fabricated arrival date.
    from service.database import Job

    with client.app.state.sessions.begin() as session:
        session.get(Job, job_id).result = {**saved, "received_at": None}
    assert client.post("/api/agent/results", headers=auth, json=upload).json()["duplicate"] is True
    assert client.get(f"/api/jobs/{job_id}", headers=admin).json()["result"]["received_at"] is None
    import secrets

    next_credential = secrets.token_urlsafe(32)
    assert (
        client.post(
            "/api/agent/rotate", headers=auth, json={"credential": next_credential}
        ).status_code
        == 200
    )
    assert client.post("/api/agent/poll", headers=auth).status_code == 401
    auth = {"Authorization": "Bearer " + next_credential}
    assert client.post(
        "/api/agent/rotate", headers=auth, json={"credential": next_credential}
    ).json() == {"rotated": True}
    assert client.delete(f"/api/agents/{agent['agent_id']}", headers=admin).status_code == 204
    assert client.post("/api/agent/poll", headers=auth).status_code == 401
    assert client.post("/api/agent/results", headers=auth, json=upload).status_code == 401
