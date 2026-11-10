"""Expire undelivered work without fabricating probe measurements."""

from datetime import timedelta

from sqlalchemy import or_, select, update

from service.audit import record_audit
from service.database import Job

AGENT_QUEUE_MAX_AGE = timedelta(seconds=120)
CLOUD_QUEUE_MAX_AGE = timedelta(seconds=120)


def _expire_jobs(session, now, scope, max_age, action):
    # Never interrupt a live lease: an upload may still legitimately arrive.
    reclaimable = or_(
        Job.state == "queued",
        (Job.state == "running") & or_(Job.lease_until <= now, Job.lease_until.is_(None)),
    )
    eligible = scope & reclaimable & or_(Job.created_at < now - max_age, Job.attempts >= 3)
    candidates = select(Job.id).where(eligible).order_by(Job.created_at, Job.id).limit(500)
    expired = session.execute(
        update(Job)
        .where(Job.id.in_(candidates), eligible)
        .values(state="failed", lease_token=None, lease_until=None)
        .returning(Job.id, Job.workspace)
    ).all()
    for job_id, workspace in expired:
        record_audit(session, workspace, action, job_id, "lifecycle")
    return len(expired)


def expire_agent_jobs(session, now, agent_id=None):
    scope = Job.agent_id.is_not(None)
    if agent_id is not None:
        scope &= Job.agent_id == agent_id
    return _expire_jobs(session, now, scope, AGENT_QUEUE_MAX_AGE, "agent_job.delivery_expired")


def expire_cloud_jobs(session, now, workspace=None):
    scope = Job.agent_id.is_(None)
    if workspace is not None:
        scope &= Job.workspace == workspace
    return _expire_jobs(session, now, scope, CLOUD_QUEUE_MAX_AGE, "cloud_job.delivery_expired")
