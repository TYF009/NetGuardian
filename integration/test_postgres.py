"""Opt-in tests against a disposable local PostgreSQL database only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select

from probe_core.contracts import Measurement, configuration_hash
from probe_core.policy import CloudPolicy
from service.database import Base, Job, Workspace
from service.schema import require_schema
from service.worker import run_once


def test_postgres_migrations_match_metadata(postgres):
    engine, _ = postgres
    require_schema(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_postgres_concurrent_workers_do_not_duplicate_claims(postgres):
    _, sessions = postgres
    workspace = "integration-" + str(uuid4())
    with sessions.begin() as session:
        session.add(Workspace(id=workspace))
        for _ in range(12):
            session.add(
                Job(
                    workspace=workspace,
                    kind="dns",
                    target="https://example.com",
                    policy_version="v1",
                )
            )
    observed = []
    lock = Lock()

    async def execute(request, policy, vantage):
        with lock:
            observed.append(str(request.job_id))
        await asyncio.sleep(0.02)
        return Measurement(
            job_id=request.job_id,
            attempt=1,
            kind=request.kind,
            target=request.target,
            vantage_id=vantage,
            configuration_hash=configuration_hash(request),
            observed_at=datetime.now(UTC),
            probe_version="integration",
            policy_version=policy.version,
            status="success",
        )

    def worker():
        for _ in range(20):
            asyncio.run(
                run_once(sessions, {workspace: CloudPolicy("v1")}, execute, vantage_id=uuid4())
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: worker(), range(4)))
    with sessions() as session:
        jobs = session.scalars(select(Job).where(Job.workspace == workspace)).all()
        assert len(observed) == len(set(observed)) == len(jobs) == 12
        assert all(job.state == "succeeded" and job.attempts == 1 for job in jobs)
        assert all(job.result["attempt"] == 1 for job in jobs)


def test_postgres_concurrent_workspace_initialization(postgres):
    from threading import Barrier

    from service.database import initialize_workspaces

    engine, sessions = postgres
    names = ["integration-" + str(uuid4()) for _ in range(2)]
    barrier = Barrier(4)

    def start(index):
        barrier.wait(timeout=5)
        initialize_workspaces(engine, names if index % 2 else reversed(names))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(start, range(4)))
    with sessions() as session:
        rows = session.scalars(select(Workspace).where(Workspace.id.in_(names))).all()
        assert len(rows) == 2


def test_postgres_rejects_cross_workspace_agent_assignment(postgres):
    from sqlalchemy.exc import IntegrityError

    from service.database import Agent

    _, sessions = postgres
    one, two, agent_id = (str(uuid4()) for _ in range(3))
    with sessions.begin() as session:
        session.add_all(
            [
                Workspace(id=one),
                Workspace(id=two),
                Agent(id=agent_id, workspace=two, name="Fixture", credential_hash=agent_id),
            ]
        )
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            Job(
                workspace=one,
                agent_id=agent_id,
                kind="dns",
                target="https://example.com",
                policy_version="fixture",
            )
        )


def test_postgres_retention_preserves_evidence_pairs_and_tenants(postgres):
    from datetime import timedelta

    from service.database import DiagnosticPair, Incident, Monitor, MonitorRun
    from service.retention import prune

    _, sessions = postgres
    workspace, other = str(uuid4()), str(uuid4())
    old = datetime.now(UTC) - timedelta(days=60)
    with sessions.begin() as session:
        session.add_all([Workspace(id=workspace), Workspace(id=other)])
        monitor = Monitor(
            workspace=workspace, name="Retention", kind="dns", target="https://example.com"
        )
        session.add(monitor)
        session.flush()
        ids = []
        for index in range(103):
            job = Job(
                workspace=workspace,
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
                MonitorRun(workspace=workspace, job_id=job.id, monitor_id=monitor.id, processed=1)
            )
        session.add(Incident(workspace=workspace, monitor_id=monitor.id, evidence=[ids[0]]))
        extras = []
        for owner, state in [
            (workspace, "succeeded"),
            (workspace, "failed"),
            (workspace, "queued"),
            (other, "succeeded"),
        ]:
            job = Job(
                workspace=owner,
                kind="dns",
                target=monitor.target,
                policy_version="v1",
                state=state,
                created_at=old,
            )
            session.add(job)
            session.flush()
            extras.append(job.id)
        session.add(
            DiagnosticPair(workspace=workspace, cloud_job_id=extras[0], agent_job_id=extras[1])
        )
    assert prune(sessions, workspace)["job_ids"] == ids[1:3]
    with sessions() as session:
        assert session.get(Job, ids[1]) is not None
        assert session.get(Job, extras[0]).created_at.utcoffset() == timedelta(0)
    assert prune(sessions, workspace, apply=True)["job_ids"] == ids[1:3]
    with sessions() as session:
        assert all(
            session.get(Job, identifier) is not None for identifier in [ids[0], *ids[3:], *extras]
        )
        assert all(session.get(Job, identifier) is None for identifier in ids[1:3])
        assert all(session.get(MonitorRun, identifier) is None for identifier in ids[1:3])
    assert prune(sessions, workspace, apply=True)["count"] == 0
    # Shared integration database: leave no runnable fixture work for later workers.
    with sessions.begin() as session:
        session.get(Job, extras[2]).state = "cancelled"


def test_postgres_retention_and_result_processing_do_not_deadlock(postgres, monkeypatch):
    from threading import Event, local

    from sqlalchemy import event

    from service import monitoring
    from service.database import IncidentEvidence, Monitor, MonitorRun
    from service.retention import prune

    engine, sessions = postgres
    workspace = str(uuid4())
    with sessions.begin() as session:
        session.add(Workspace(id=workspace))
        monitor = Monitor(
            workspace=workspace,
            name="Lock order fixture",
            kind="http",
            target="https://example.com",
            enabled=0,
            open_after=1,
        )
        session.add(monitor)
        session.flush()
        job = Job(
            workspace=workspace,
            kind="http",
            target=monitor.target,
            policy_version="v1",
            state="succeeded",
            result={"status": "success", "http_status": 503},
        )
        session.add(job)
        session.flush()
        job_id = job.id
        session.add(MonitorRun(workspace=workspace, job_id=job_id, monitor_id=monitor.id))
    monitor_locked, workspace_locked = Event(), Event()
    marker = local()
    original = monitoring.apply_result

    def synchronized_apply(session, job):
        original(session, job)
        if job.id == job_id:
            monitor_locked.set()
            assert workspace_locked.wait(5), "Retention did not acquire workspace lock"

    def on_statement(connection, cursor, statement, parameters, context, many):
        if getattr(marker, "retention", False) and statement.startswith("UPDATE workspaces"):
            workspace_locked.set()

    def retention():
        assert monitor_locked.wait(5), "Result processing did not acquire monitor lock"
        marker.retention = True
        return prune(sessions, workspace, apply=True)

    monkeypatch.setattr(monitoring, "apply_result", synchronized_apply)
    event.listen(engine, "after_cursor_execute", on_statement)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cleanup = pool.submit(retention)
            scheduler = pool.submit(monitoring.tick, sessions, {})
            scheduler.result(timeout=15)
            assert cleanup.result(timeout=15)["count"] == 0
    finally:
        event.remove(engine, "after_cursor_execute", on_statement)
    with sessions() as session:
        assert session.get(MonitorRun, job_id).processed == 1
        assert (
            session.scalar(select(IncidentEvidence.job_id).where(IncidentEvidence.job_id == job_id))
            == job_id
        )
