"""Long incidents retain every link while list/report summaries remain bounded."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from service.api import create_app
from service.database import (
    Incident,
    IncidentEvidence,
    Job,
    Monitor,
    MonitorRun,
    Workspace,
    database,
)
from service.monitoring import apply_result
from service.retention import prune
from service.schema import upgrade
from service.settings import Settings


def test_long_incident_history_pagination_and_retention(tmp_path):
    url = f"sqlite:///{tmp_path / 'long.db'}"
    upgrade(url)
    app = create_app(Settings(url, {"a" * 32: "one", "b" * 32: "two"}, {}))
    identifiers = []
    with app.state.sessions.begin() as session:
        monitor = Monitor(
            workspace="one", name="Fixture", kind="http", target="https://example.com", open_after=1
        )
        session.add(monitor)
        session.flush()
        for _ in range(1002):
            job = Job(
                workspace="one",
                kind="http",
                target=monitor.target,
                policy_version="v1",
                state="succeeded",
                created_at=datetime.now(UTC) - timedelta(days=60),
                result={"status": "success", "http_status": 503},
            )
            session.add(job)
            session.flush()
            identifiers.append(job.id)
            session.add(MonitorRun(workspace="one", monitor_id=monitor.id, job_id=job.id))
            session.flush()
            apply_result(session, job)
        incident = session.scalar(select(Incident))
        incident_id = incident.id
        assert incident.evidence == identifiers[-1000:]
    assert prune(app.state.sessions, "one", apply=True)["count"] == 0
    client = TestClient(app)
    path = f"/api/incidents/{incident_id}/evidence"
    auth = {"Authorization": "Bearer " + "a" * 32}
    assert client.get(path, headers={"Authorization": "Bearer " + "b" * 32}).status_code == 404
    assert client.get(path + "?limit=101", headers=auth).status_code == 422
    seen, after = [], 0
    while True:
        response = client.get(path, params={"after": after}, headers=auth)
        assert response.status_code == 200
        page = response.json()
        seen.extend(item["job_id"] for item in page["items"])
        after = page["next_after"]
        if after is None:
            break
    assert seen == identifiers


def test_migration_preserves_existing_missing_links(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "ce2d9e13a712")
    engine, sessions = database(url)
    incident_id, monitor_id = str(uuid4()), str(uuid4())
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        session.add(
            Monitor(
                id=monitor_id,
                workspace="one",
                name="Fixture",
                kind="dns",
                target="https://example.com",
            )
        )
        session.add(
            Incident(
                id=incident_id,
                workspace="one",
                monitor_id=monitor_id,
                evidence=["missing-1", "missing-2"],
            )
        )
    upgrade(url)
    with sessions() as session:
        rows = session.scalars(select(IncidentEvidence).order_by(IncidentEvidence.position)).all()
        assert [(row.position, row.job_id) for row in rows] == [(1, "missing-1"), (2, "missing-2")]
    engine.dispose()
