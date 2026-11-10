"""Persistent API behavior, tenant isolation and worker integration."""

import asyncio
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from probe_core.contracts import Measurement
from probe_core.policy import CloudPolicy
from service.api import create_app
from service.schema import upgrade
from service.settings import Settings
from service.worker import run_once


def test_job_lifecycle_and_isolation(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'test.db'}",
        {"a" * 32: "one", "b" * 32: "two"},
        {"one": CloudPolicy("v1", frozenset({("example.com", 443, "https")}))},
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    one, two = {"Authorization": "Bearer " + "a" * 32}, {"Authorization": "Bearer " + "b" * 32}
    assert client.get("/api/jobs").status_code in (401, 403)
    assert (
        client.post(
            "/api/jobs", headers=one, json={"kind": "http", "target": "https://evil.test"}
        ).status_code
        == 403
    )
    response = client.post(
        "/api/jobs", headers=one, json={"kind": "dns", "target": "https://example.com"}
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/jobs/{job_id}", headers=two).status_code == 404
    assert client.get("/api/jobs", headers=two).json() == []

    async def execute(request, policy, vantage):
        return Measurement(
            job_id=UUID(job_id),
            attempt=1,
            kind="dns",
            vantage_id=vantage,
            target=request.target,
            configuration_hash="a" * 64,
            observed_at="2026-11-04T00:00:00Z",
            probe_version="test",
            policy_version=policy.version,
            status="success",
        )

    assert asyncio.run(run_once(app.state.sessions, settings.policies, execute, vantage_id=uuid4()))
    assert not asyncio.run(
        run_once(app.state.sessions, settings.policies, execute, vantage_id=uuid4())
    )
    detail = client.get(f"/api/jobs/{job_id}", headers=one).json()
    assert detail["state"] == "succeeded"
    # Recreate the API against the same database to verify persistence.
    restarted = TestClient(create_app(settings))
    assert restarted.get(f"/api/jobs/{job_id}", headers=one).json() == detail
    for _ in range(20):
        assert (
            client.post(
                "/api/jobs", headers=one, json={"kind": "dns", "target": "https://example.com"}
            ).status_code
            == 202
        )
    assert (
        client.post(
            "/api/jobs", headers=one, json={"kind": "dns", "target": "https://example.com"}
        ).status_code
        == 429
    )
