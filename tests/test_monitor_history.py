"""Monitor history distinguishes missing measurements and zero timings."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from service.api import create_app
from service.database import Job, Monitor, MonitorRun
from service.schema import upgrade
from service.settings import Settings


def test_history_is_bounded_scoped_and_preserves_zero(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'history.db'}", {"a" * 32: "one", "b" * 32: "two"}, {}
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    now = datetime.now(UTC)
    with app.state.sessions.begin() as session:
        monitor = Monitor(
            workspace="one", name="Fixture", kind="http", target="https://example.com"
        )
        session.add(monitor)
        session.flush()
        monitor_id = monitor.id
        for index in range(102):
            job = Job(
                workspace="one",
                kind="http",
                target=monitor.target,
                policy_version="v1",
                state="failed",
                created_at=now + timedelta(seconds=index),
                result=None
                if index == 101
                else {"status": "error", "timings": {"http_total_ms": 0}},
            )
            session.add(job)
            session.flush()
            session.add(
                MonitorRun(
                    workspace=job.workspace, job_id=job.id, monitor_id=monitor_id, processed=1
                )
            )
    path = f"/api/monitors/{monitor_id}/runs"
    assert client.get(path, headers={"Authorization": "Bearer " + "b" * 32}).status_code == 404
    response = client.get(path, headers={"Authorization": "Bearer " + "a" * 32})
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert len(runs) == 100
    assert runs[0]["timings"]["http_total_ms"] == 0
    assert runs[-1]["timings"] == {} and runs[-1]["status"] is None
    assert datetime.fromisoformat(runs[0]["created_at"].replace("Z", "+00:00")) == now + timedelta(
        seconds=2
    )
