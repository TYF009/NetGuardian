"""Shared admission budget; callers must hold the workspace transaction lock."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from service.database import Job

JOBS_PER_MINUTE = 60


def within_job_rate(session, workspace, requested=1, now=None):
    cutoff = (now or datetime.now(UTC)) - timedelta(seconds=60)
    recent = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.workspace == workspace, Job.created_at > cutoff)
    )
    return recent + requested <= JOBS_PER_MINUTE
