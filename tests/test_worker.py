"""Worker retries must preserve truthful evidence and discard expired leases."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from probe_core.contracts import Measurement
from probe_core.policy import CloudPolicy
from service.database import Job, Workspace, database
from service.schema import upgrade
from service.worker import run_once


def setup_job(tmp_path):
    url = f"sqlite:///{tmp_path / 'worker.db'}"
    upgrade(url)
    engine, sessions = database(url)
    with sessions.begin() as session:
        session.add(Workspace(id="one"))
        job = Job(
            workspace="one",
            kind="dns",
            target="https://example.com",
            policy_version="v1",
            state="running",
            attempts=1,
            lease_token=str(uuid4()),
            lease_until=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(job)
        session.flush()
        job_id = job.id
    return engine, sessions, job_id


def evidence(request, policy, vantage):
    return Measurement(
        job_id=request.job_id,
        attempt=1,
        kind=request.kind,
        target=request.target,
        vantage_id=vantage,
        configuration_hash="a" * 64,
        observed_at=datetime.now(UTC),
        probe_version="test",
        policy_version=policy.version,
        status="success",
    )


def test_reclaimed_job_records_actual_attempt(tmp_path):
    engine, sessions, job_id = setup_job(tmp_path)

    async def execute(request, policy, vantage):
        assert request.job_id == UUID(job_id)
        return evidence(request, policy, vantage)

    assert asyncio.run(run_once(sessions, {"one": CloudPolicy("v1")}, execute, vantage_id=uuid4()))
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job.attempts == 2
        assert job.result["attempt"] == 2
        received = datetime.fromisoformat(job.result["received_at"].replace("Z", "+00:00"))
        observed = datetime.fromisoformat(job.result["observed_at"].replace("Z", "+00:00"))
        assert observed <= received <= datetime.now(UTC)
        assert job.state == "succeeded"
    engine.dispose()


def test_expired_lease_cannot_publish_result(tmp_path):
    engine, sessions, job_id = setup_job(tmp_path)

    async def execute(request, policy, vantage):
        with sessions.begin() as session:
            job = session.get(Job, job_id)
            job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        return evidence(request, policy, vantage)

    assert asyncio.run(run_once(sessions, {"one": CloudPolicy("v1")}, execute, vantage_id=uuid4()))
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job.result is None
        assert job.state == "running"
    engine.dispose()


def test_worker_location_configuration(monkeypatch):
    import pytest

    from service.worker import configured_vantage

    for invalid in ("", "not-a-uuid", str(UUID(int=0))):
        monkeypatch.setenv("NETGUARDIAN_VANTAGE_ID", invalid)
        with pytest.raises(ValueError, match="NETGUARDIAN_VANTAGE_ID"):
            configured_vantage()
    expected = uuid4()
    monkeypatch.setenv("NETGUARDIAN_VANTAGE_ID", str(expected))
    assert configured_vantage() == expected
    assert configured_vantage() == expected


def test_worker_persists_configured_location(tmp_path):
    engine, sessions, job_id = setup_job(tmp_path)
    location = uuid4()

    async def execute(request, policy, vantage):
        assert vantage == location
        return evidence(request, policy, vantage)

    asyncio.run(run_once(sessions, {"one": CloudPolicy("v1")}, execute, vantage_id=location))
    with sessions() as session:
        assert session.get(Job, job_id).result["vantage_id"] == str(location)
    engine.dispose()
