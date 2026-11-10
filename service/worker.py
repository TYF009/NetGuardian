"""Single-concurrency worker with atomic leases and bounded crash retries."""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update

from probe_core.contracts import ProbeRequest
from probe_core.executor import execute_probe
from probe_core.policy import CloudPolicy
from service.database import Job, database
from service.job_lifecycle import CLOUD_QUEUE_MAX_AGE, expire_cloud_jobs
from service.monitoring import apply_result, tick
from service.schema import require_schema
from service.settings import Settings


def configured_vantage():
    try:
        value = UUID(os.environ.get("NETGUARDIAN_VANTAGE_ID", ""))
        if value.int == 0:
            raise ValueError("Nil UUID is not a probe identity")
        return value
    except ValueError:
        raise ValueError(
            "Set NETGUARDIAN_VANTAGE_ID to a stable, non-nil UUID for this probe location"
        ) from None


async def run_once(sessions, policies, execute=execute_probe, *, vantage_id: UUID):
    now = datetime.now(UTC)
    eligible = (
        (Job.agent_id.is_(None))
        & (Job.created_at >= now - CLOUD_QUEUE_MAX_AGE)
        & or_(Job.state == "queued", (Job.state == "running") & (Job.lease_until < now))
    )
    with sessions.begin() as session:
        expire_cloud_jobs(session, now)
        session.execute(
            update(Job)
            .execution_options(synchronize_session="fetch")
            .where(eligible, Job.attempts >= 3)
            .values(state="failed")
        )
        job = session.scalar(
            select(Job).where(eligible, Job.attempts < 3).order_by(Job.created_at).limit(1)
        )
        if job is None:
            return False
        token = str(uuid4())
        claimed = session.execute(
            update(Job)
            .execution_options(synchronize_session="fetch")
            .where(Job.id == job.id, eligible)
            .values(
                state="running",
                lease_token=token,
                lease_until=now + timedelta(seconds=30),
                attempts=Job.attempts + 1,
            )
        )
        if claimed.rowcount != 1:
            return False
        job_id, tenant, kind, target, version, attempt = (
            job.id,
            job.workspace,
            job.kind,
            job.target,
            job.policy_version,
            job.attempts,
        )
    policy = policies.get(tenant, CloudPolicy("revoked"))
    result = await execute(
        ProbeRequest(job_id=UUID(job_id), kind=kind, target=target, policy_version=version),
        policy,
        vantage_id,
    )
    result = result.model_copy(update={"attempt": attempt, "received_at": datetime.now(UTC)})
    with sessions.begin() as session:
        completed = session.execute(
            update(Job)
            .execution_options(synchronize_session="fetch")
            .where(
                Job.id == job_id,
                Job.lease_token == token,
                Job.state == "running",
                Job.lease_until > datetime.now(UTC),
            )
            .values(
                state="succeeded" if result.status == "success" else "failed",
                result=result.model_dump(mode="json"),
                lease_until=None,
                lease_token=None,
            )
        )
        if completed.rowcount == 1:
            apply_result(session, session.get(Job, job_id))
    return True


async def main():
    vantage_id = configured_vantage()
    settings = Settings.from_environment()
    engine, sessions = database(settings.database_url)
    require_schema(engine)
    while True:
        try:
            tick(sessions, settings.policies)
            if not await run_once(sessions, settings.policies, vantage_id=vantage_id):
                await asyncio.sleep(1)
        except Exception:
            logging.exception("Worker attempt failed; lease will expire before retry")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
