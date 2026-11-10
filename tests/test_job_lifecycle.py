"""Offline agents release queue capacity, never imply target failure or recovery."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from probe_core.policy import CloudPolicy
from service.database import (
    Agent,
    AuditEvent,
    Base,
    Incident,
    Job,
    Monitor,
    MonitorRun,
    Workspace,
    database,
)
from service.job_lifecycle import expire_agent_jobs
from service.monitoring import tick


def test_expiry_preserves_active_leases_and_is_scoped(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'expiry.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(Workspace(id="workspace"))
        session.add_all(
            [
                Agent(id=name, workspace="workspace", name=name, credential_hash=name)
                for name in ("one", "two")
            ]
        )

        def add(agent="one", state="queued", age=121, lease=None, attempts=0):
            job = Job(
                workspace="workspace",
                agent_id=agent,
                kind="dns",
                target="https://example.com",
                policy_version="v1",
                state=state,
                created_at=now - timedelta(seconds=age),
                lease_until=lease,
                attempts=attempts,
            )
            session.add(job)
            return job

        expired = add()
        other = add(agent="two")
        cloud = add(agent=None)
        recent = add(age=119)
        live = add(state="running", lease=now + timedelta(seconds=1))
        stale = add(state="running", lease=now - timedelta(seconds=1))
        exhausted = add(state="running", age=60, lease=now - timedelta(seconds=1), attempts=3)
        done = add(state="succeeded")
        session.flush()
        assert expire_agent_jobs(session, now, "one") == 3
        for job in (expired, stale, exhausted):
            session.refresh(job)
            assert job.state == "failed" and job.result is None
            assert job.lease_token is None and job.lease_until is None
        for job, state in (
            (other, "queued"),
            (cloud, "queued"),
            (recent, "queued"),
            (live, "running"),
            (done, "succeeded"),
        ):
            session.refresh(job)
            assert job.state == state
        assert expire_agent_jobs(session, now, "one") == 0
        assert len(session.scalars(select(AuditEvent)).all()) == 3


def test_scheduler_replaces_expired_run_without_incident_transition(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path / 'schedule.db'}")
    Base.metadata.create_all(engine)
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        agent = Agent(workspace="one", name="Offline", credential_hash="fixture")
        session.add(agent)
        session.flush()
        monitor = Monitor(
            workspace="one",
            agent_id=agent.id,
            name="Test",
            kind="dns",
            target="https://example.com",
            failure_count=2,
        )
        session.add(monitor)
        session.flush()
        job = Job(
            workspace="one",
            agent_id=agent.id,
            kind="dns",
            target=monitor.target,
            policy_version="v1",
            created_at=datetime.now(UTC) - timedelta(seconds=121),
        )
        incident = Incident(workspace="one", monitor_id=monitor.id, evidence=[])
        session.add_all([job, incident])
        session.flush()
        session.add(MonitorRun(workspace=job.workspace, job_id=job.id, monitor_id=monitor.id))
        old_id, monitor_id = job.id, monitor.id
    tick(sessions, {"one": CloudPolicy("v1")})
    with sessions() as session:
        assert session.get(Job, old_id).state == "failed"
        assert session.get(MonitorRun, old_id).processed == 1
        assert session.get(Monitor, monitor_id).failure_count == 0
        assert len(session.scalars(select(Job).where(Job.state == "queued")).all()) == 1
        incident = session.scalar(select(Incident))
        assert incident.state == "open" and incident.recovered_at is None
        assert incident.evidence == [old_id]
