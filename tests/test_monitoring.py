"""Durable scheduler and incident behavior with explicit synthetic evidence."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.database import Base, Incident, Job, Monitor, MonitorRun, Workspace, database
from service.monitoring import apply_result, telemetry_state, tick


def test_schedule_deduplication_and_incident_recovery(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'monitor.db'}")
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        monitor = Monitor(
            workspace="one",
            name="Test",
            target="https://example.com",
            kind="http",
            open_after=2,
            recover_after=2,
        )
        session.add(monitor)
        session.flush()
        monitor_id = monitor.id
    policies = {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))}
    job_ids = []
    for status in (503, 503, 200, 200):
        tick(sessions, policies)
        tick(sessions, policies)
        with sessions.begin() as session:
            queued = session.scalars(select(Job).where(Job.state == "queued")).all()
            assert len(queued) == 1
            job = queued[0]
            job_ids.append(job.id)
            job.state = "succeeded"
            job.result = {"status": "success", "http_status": status}
            apply_result(session, job)
            apply_result(session, job)  # Duplicate delivery must not advance thresholds.
            monitor = session.get(Monitor, monitor_id)
            monitor.next_due = datetime.now(UTC) - timedelta(seconds=1)
    with sessions() as session:
        incident = session.scalar(select(Incident))
        assert incident.state == "recovered"
        assert incident.recovered_at is not None
        assert incident.evidence == job_ids
        assert len(session.scalars(select(MonitorRun)).all()) == 4


def test_missing_telemetry_breaks_streak_without_recovery(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'missing.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        monitor = Monitor(
            workspace="one",
            name="Fixture",
            target="https://example.com",
            kind="http",
            next_due=now,
            enabled=1,
            interval_seconds=60,
            failure_count=2,
            success_count=1,
        )
        session.add(monitor)
        session.flush()
        assert telemetry_state(session, monitor, now)["state"] == "awaiting_first_run"
        assert telemetry_state(session, monitor, now + timedelta(seconds=31))["state"] == "missing"
        incident = Incident(workspace="one", monitor_id=monitor.id, state="open", evidence=[])
        job = Job(
            workspace="one",
            kind="http",
            target=monitor.target,
            policy_version="v1",
            state="queued",
            created_at=now,
        )
        session.add_all([job, incident])
        session.flush()
        session.add(MonitorRun(workspace=job.workspace, job_id=job.id, monitor_id=monitor.id))
        session.flush()
        assert telemetry_state(session, monitor, now)["state"] == "pending"
        assert telemetry_state(session, monitor, now + timedelta(seconds=121))["state"] == "missing"
        job.state = "failed"
        apply_result(session, job)
        assert monitor.failure_count == monitor.success_count == 0
        assert incident.state == "open"
        assert incident.recovered_at is None
        assert incident.evidence == [job.id]
        assert telemetry_state(session, monitor, now)["state"] == "missing"
        job.result = {"status": "denied"}
        assert telemetry_state(session, monitor, now)["state"] == "unavailable"
        job.result = {"status": "success", "http_status": 503}
        assert telemetry_state(session, monitor, now)["state"] == "current"
        assert telemetry_state(session, monitor, now + timedelta(seconds=181))["state"] == "stale"
        monitor.enabled = 0
        assert telemetry_state(session, monitor, now)["state"] == "paused"
    engine.dispose()
