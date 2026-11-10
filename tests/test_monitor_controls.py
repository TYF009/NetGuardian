"""Pause/resume authorization, idempotency and bounded scheduling."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.api import create_app
from service.database import Job, Monitor
from service.monitoring import tick
from service.schema import upgrade
from service.settings import Settings


def test_pause_resume_preserves_history_and_does_not_catch_up(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'controls.db'}",
        {"a" * 32: "one", "b" * 32: "two"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    auth = {"Authorization": "Bearer " + "a" * 32}
    other = {"Authorization": "Bearer " + "b" * 32}
    created = client.post(
        "/api/monitors",
        headers=auth,
        json={"name": "Fixture", "target": "https://example.com", "kind": "http"},
    )
    assert created.status_code == 201
    monitor_id = created.json()["id"]
    path = f"/api/monitors/{monitor_id}"
    assert client.patch(path, headers=other, json={"enabled": False}).status_code == 404
    assert client.patch(path, headers=auth, json={"enabled": "false"}).status_code == 422
    assert client.patch(path, headers=auth, json={"enabled": False}).json()["enabled"] is False
    tick(app.state.sessions, settings.policies)
    with app.state.sessions.begin() as session:
        assert session.scalars(select(Job)).all() == []
        monitor = session.get(Monitor, monitor_id)
        monitor.next_due = datetime.now(UTC) - timedelta(days=3)
        monitor.failure_count = 2
    assert client.patch(path, headers=auth, json={"enabled": True}).json()["enabled"] is True
    with app.state.sessions() as session:
        monitor = session.get(Monitor, monitor_id)
        assert monitor.failure_count == 0
        due = monitor.next_due
    assert client.patch(path, headers=auth, json={"enabled": True}).status_code == 200
    with app.state.sessions() as session:
        assert session.get(Monitor, monitor_id).next_due == due
    tick(app.state.sessions, settings.policies)
    tick(app.state.sessions, settings.policies)
    with app.state.sessions() as session:
        assert len(session.scalars(select(Job)).all()) == 1
    assert client.delete(path, headers=auth).status_code == 204
    settings.policies.clear()
    assert client.patch(path, headers=auth, json={"enabled": True}).status_code == 403
    with app.state.sessions() as session:
        assert session.get(Monitor, monitor_id).enabled == 0
        assert len(session.scalars(select(Job)).all()) == 1
