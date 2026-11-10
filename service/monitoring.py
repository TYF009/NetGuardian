"""Durable schedules and evidence-linked incident transitions."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from service.database import Agent, Incident, IncidentEvidence, Job, Monitor, MonitorRun, Workspace
from service.job_lifecycle import expire_agent_jobs, expire_cloud_jobs
from service.quotas import within_job_rate


def tick(sessions, policies):
    now = datetime.now(UTC)
    with sessions.begin() as session:
        expire_agent_jobs(session, now)
        expire_cloud_jobs(session, now)
        for job in session.scalars(
            select(Job)
            .join(MonitorRun, MonitorRun.job_id == Job.id)
            .where(Job.state.in_(["succeeded", "failed"]), MonitorRun.processed == 0)
            .order_by(MonitorRun.monitor_id, Job.created_at, Job.id)
        ).all():
            apply_result(session, job)
    # Release result/monitor locks before acquiring workspace locks. Retention takes
    # workspace then monitor locks; retaining both phases would reverse that order.
    with sessions.begin() as session:
        # Serialize each workspace's scheduler and submission quotas across processes.
        for workspace in session.scalars(select(Workspace).order_by(Workspace.id)).all():
            session.execute(
                update(Workspace)
                .where(Workspace.id == workspace.id)
                .values(revision=Workspace.revision + 1)
            )
            for monitor in session.scalars(
                select(Monitor).where(
                    Monitor.workspace == workspace.id, Monitor.enabled == 1, Monitor.next_due <= now
                )
            ).all():
                if monitor.agent_id is not None:
                    agent = session.scalar(
                        select(Agent).where(
                            Agent.id == monitor.agent_id,
                            Agent.workspace == workspace.id,
                            Agent.revoked == 0,
                        )
                    )
                    if agent is None:
                        monitor.enabled = 0
                        continue
                pending = session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.workspace == workspace.id, Job.state.in_(["queued", "running"]))
                )
                active = session.scalar(
                    select(func.count())
                    .select_from(MonitorRun)
                    .join(Job, Job.id == MonitorRun.job_id)
                    .where(MonitorRun.monitor_id == monitor.id, MonitorRun.processed == 0)
                )
                if pending >= 20 or active or not within_job_rate(session, workspace.id):
                    continue
                policy = policies.get(workspace.id)
                if policy is None:
                    continue
                job = Job(
                    workspace=workspace.id,
                    agent_id=monitor.agent_id,
                    kind=monitor.kind,
                    target=monitor.target,
                    policy_version=policy.version,
                )
                session.add(job)
                session.flush()
                session.add(
                    MonitorRun(workspace=job.workspace, job_id=job.id, monitor_id=monitor.id)
                )
                # No historical catch-up storm after downtime.
                monitor.next_due = now + timedelta(seconds=monitor.interval_seconds)


def apply_result(session, job):
    run = session.get(MonitorRun, job.id)
    if run is None or run.processed:
        return
    claimed = session.execute(
        update(MonitorRun)
        .where(MonitorRun.job_id == job.id, MonitorRun.processed == 0)
        .values(processed=1)
    )
    if claimed.rowcount != 1:
        return
    session.execute(
        update(Monitor).where(Monitor.id == run.monitor_id).values(enabled=Monitor.enabled)
    )
    monitor = session.get(Monitor, run.monitor_id)
    run.processed = 1
    incident = session.scalar(
        select(Incident).where(
            Incident.monitor_id == monitor.id,
            Incident.workspace == monitor.workspace,
            Incident.state == "open",
        )
    )
    if incident is not None:
        append_incident_links(session, incident, [job.id])
        incident.evidence = [*incident.evidence, job.id][-1000:]
    result = job.result
    if result is None:
        # Missing telemetry breaks consecutive evidence; it is not recovery.
        monitor.failure_count = monitor.success_count = 0
        return
    healthy = result["status"] == "success" and (
        result.get("http_status") is None or 200 <= result["http_status"] < 400
    )
    if result["status"] in {"denied", "unsupported", "cancelled"}:
        monitor.failure_count = monitor.success_count = 0
        return
    monitor.failure_count = 0 if healthy else monitor.failure_count + 1
    monitor.success_count = monitor.success_count + 1 if healthy else 0
    if incident is None and monitor.failure_count >= monitor.open_after:
        # The scheduler permits one unfinished run per monitor. Retrieve the preceding
        # processed runs in that serial sequence, excluding the current observation.
        previous = session.scalars(
            select(Job)
            .join(MonitorRun, MonitorRun.job_id == Job.id)
            .where(
                MonitorRun.monitor_id == monitor.id,
                MonitorRun.processed == 1,
                Job.workspace == monitor.workspace,
                Job.id != job.id,
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(max(0, min(monitor.open_after, 20) - 1))
        ).all()
        incident = Incident(
            workspace=monitor.workspace,
            monitor_id=monitor.id,
            evidence=[item.id for item in reversed(previous)] + [job.id],
        )
        session.add(incident)
        session.flush()
        append_incident_links(session, incident, incident.evidence)
    if incident is not None and healthy and monitor.success_count >= monitor.recover_after:
        incident.state = "recovered"
        incident.recovered_at = datetime.now(UTC)


def telemetry_state(session, monitor, now=None):
    """Describe collection freshness independently of observed target health."""
    now = now or datetime.now(UTC)
    latest = session.scalar(
        select(Job)
        .join(MonitorRun, MonitorRun.job_id == Job.id)
        .where(MonitorRun.monitor_id == monitor.id, Job.workspace == monitor.workspace)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )

    def aware(value):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    if not monitor.enabled:
        state = "paused"
    elif latest is None:
        state = (
            "missing"
            if now > aware(monitor.next_due) + timedelta(seconds=30)
            else "awaiting_first_run"
        )
    elif latest.state in {"queued", "running"}:
        state = "missing" if now > aware(latest.created_at) + timedelta(seconds=120) else "pending"
    elif latest.result is None:
        state = "missing"
    elif now > aware(latest.created_at) + timedelta(seconds=monitor.interval_seconds + 120):
        state = "stale"
    elif latest.result.get("status") in {"denied", "unsupported", "cancelled"}:
        state = "unavailable"
    else:
        state = "current"
    return {
        "state": state,
        "latest_job_id": latest.id if latest else None,
        "latest_job_created_at": aware(latest.created_at) if latest else None,
    }


def append_incident_links(session, incident, identifiers):
    # apply_result holds the monitor write lock, serializing incident append positions.
    position = (
        session.scalar(
            select(func.max(IncidentEvidence.position)).where(
                IncidentEvidence.incident_id == incident.id
            )
        )
        or 0
    )
    for identifier in identifiers:
        position += 1
        session.add(
            IncidentEvidence(
                incident_id=incident.id,
                workspace=incident.workspace,
                position=position,
                job_id=identifier,
            )
        )
