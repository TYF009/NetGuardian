"""Retention preserves incident evidence, recent monitor history and pending work."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from service.database import Incident, Job, Monitor, MonitorRun, Workspace, database
from service.retention import prune
from service.schema import upgrade


def test_retention_preview_and_protected_records(tmp_path):
    url = f"sqlite:///{tmp_path / 'retention.db'}"
    upgrade(url)
    engine, sessions = database(url)
    old = datetime.now(UTC) - timedelta(days=60)
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        monitor = Monitor(workspace="one", name="Fixture", kind="dns", target="https://example.com")
        session.add(monitor)
        session.flush()
        ids = []
        for index in range(103):
            job = Job(
                workspace="one",
                kind="dns",
                target=monitor.target,
                policy_version="v1",
                state="succeeded",
                created_at=old + timedelta(seconds=index),
            )
            session.add(job)
            session.flush()
            ids.append(job.id)
            session.add(
                MonitorRun(
                    workspace=job.workspace, job_id=job.id, monitor_id=monitor.id, processed=1
                )
            )
        session.add(Incident(workspace="one", monitor_id=monitor.id, evidence=[ids[0]]))
        pending = Job(
            workspace="one",
            kind="dns",
            target=monitor.target,
            policy_version="v1",
            state="queued",
            created_at=old,
        )
        session.add(pending)
    preview = prune(sessions, "one")
    assert preview["job_ids"] == ids[1:3]
    with sessions() as session:
        assert len(session.scalars(select(Job)).all()) == 104
    applied = prune(sessions, "one", apply=True)
    assert applied["job_ids"] == preview["job_ids"]
    with sessions() as session:
        assert len(session.scalars(select(Job)).all()) == 102
        assert session.get(Job, ids[0]) is not None
        assert session.get(Job, pending.id).state == "queued"
    assert prune(sessions, "one", apply=True)["count"] == 0
    engine.dispose()
