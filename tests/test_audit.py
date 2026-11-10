"""Audit records follow transaction outcomes and workspace access boundaries."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.api import create_app
from service.audit import record_audit
from service.database import AuditEvent
from service.schema import upgrade
from service.settings import Settings


def test_audit_is_scoped_redacted_and_transactional(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'audit.db'}",
        {"a" * 32: "one", "b" * 32: "two"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    one = {"Authorization": "Bearer " + "a" * 32}
    two = {"Authorization": "Bearer " + "b" * 32}
    assert client.get("/api/audit-events").status_code in (401, 403)
    response = client.post(
        "/api/jobs",
        headers=one,
        json={"kind": "http", "target": "https://example.com/?secret=value"},
    )
    assert response.status_code == 202
    events = client.get("/api/audit-events", headers=one).json()
    assert len(events) == 1
    assert events[0]["action"] == "job.queued"
    assert events[0]["resource_id"] == response.json()["id"]
    assert "secret" not in str(events) and "example.com" not in str(events)
    assert client.get("/api/audit-events", headers=two).json() == []
    with pytest.raises(RuntimeError), app.state.sessions.begin() as session:
        record_audit(session, "one", "test.rollback", response.json()["id"])
        session.flush()
        raise RuntimeError("Deliberate rollback")
    with app.state.sessions() as session:
        assert len(session.scalars(select(AuditEvent)).all()) == 1
