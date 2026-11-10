"""An absent cloud worker cannot leave observed jobs queued indefinitely."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from service.api import create_app
from service.database import AuditEvent, Job
from service.schema import upgrade
from service.settings import Settings
from service.worker import run_once


def test_cloud_expiry_without_worker_is_scoped_and_never_fabricates_measurement(tmp_path):
    url = f"sqlite:///{tmp_path / 'cloud-expiry.db'}"
    upgrade(url)
    app = create_app(Settings(url, {"a" * 32: "one", "b" * 32: "two"}, {}))
    now = datetime.now(UTC)
    with app.state.sessions.begin() as session:

        def add(workspace, age, state="queued", lease=None):
            job = Job(
                workspace=workspace,
                kind="dns",
                target="https://example.com",
                policy_version="v1",
                state=state,
                created_at=now - timedelta(seconds=age),
                lease_until=lease,
            )
            session.add(job)
            session.flush()
            return job.id

        expired = add("one", 121)
        other = add("two", 121)
        live = add("one", 121, "running", now + timedelta(seconds=30))
        recent = add("one", 5)
    client = TestClient(app)
    auth = {"Authorization": "Bearer " + "a" * 32}
    response = client.get(f"/api/jobs/{expired}", headers=auth)
    assert response.json() == {"id": expired, "state": "failed", "result": None}
    assert client.get(f"/api/jobs/{other}", headers=auth).status_code == 404
    states = {job["id"]: job["state"] for job in client.get("/api/jobs", headers=auth).json()}
    assert states[live] == "running" and states[recent] == "queued"
    with app.state.sessions.begin() as session:
        assert session.get(Job, other).state == "queued"
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "cloud_job.delivery_expired")
        ).all()
        assert len(events) == 1 and events[0].resource_id == expired
        session.get(Job, recent).state = "cancelled"

    async def forbidden(*args):
        raise AssertionError("Expired queued jobs must never execute")

    assert not asyncio.run(run_once(app.state.sessions, {}, forbidden, vantage_id=uuid4()))
    with app.state.sessions() as session:
        assert session.get(Job, other).state == "failed"
        assert session.get(Job, other).result is None
        assert session.get(Job, live).state == "running"
