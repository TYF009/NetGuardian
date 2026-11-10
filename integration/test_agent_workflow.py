"""Real HTTPS control/probe workflow against an isolated loopback fixture.

DNS mapping, loopback authorization and test-CA trust are test overrides.
The child Agent lifecycle check substitutes credential lookup and adds crash checkpoints.
No measurement, HTTP transport, API endpoint or persistence layer is mocked.
"""

import asyncio
import json
import os
import secrets
import signal
import socket
import ssl
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import Response

from agent.client import (
    AgentConfig,
    EnrollmentResponse,
    control_request,
    process_assignment,
    rotate_credential,
    secure_keyring,
)
from agent.policy import LocalPolicy
from agent.spool import ResultSpool
from probe_core.policy import CloudPolicy, PolicyDenied
from service.api import create_app
from service.database import Monitor
from service.monitoring import tick
from service.schema import upgrade
from service.settings import Settings
from service.worker import run_once

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tls"


async def persist_then_kill(spool_path, binding, upload):
    """Kill a real spool owner after fsync/replace, before any upload acknowledgement."""
    source = """
import json, os, sys
from pathlib import Path
from agent.spool import ResultSpool
record = json.loads(sys.stdin.readline())
ResultSpool(Path(sys.argv[1]), sys.argv[2]).save(record)
print(os.getpid(), flush=True)
sys.stdin.read()
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        source,
        str(spool_path),
        binding,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[1],
    )
    owner_pid = None
    try:
        child.stdin.write((json.dumps(upload) + "\n").encode())
        await child.stdin.drain()
        ready = await asyncio.wait_for(child.stdout.readline(), timeout=10)
        assert ready.strip().isdigit(), "Spool owner did not confirm durable save"
        owner_pid = int(ready.strip())
        assert child.returncode is None
    finally:
        if owner_pid is not None:
            # The Windows venv launcher can have a different PID from Python.
            try:
                os.kill(owner_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif child.returncode is None:
            child.kill()
        child.stdin.close()
        await asyncio.wait_for(child.wait(), timeout=10)
    assert child.returncode != 0, "Expected an interrupted process, not a normal exit"
    restored = ResultSpool(spool_path, binding).load()
    assert restored == upload
    assert not list(spool_path.parent.glob(".pending-*"))
    return restored


async def run_agent_until_killed(config_path, credential, mode):
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "integration.agent_process_fixture",
        str(config_path),
        mode,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[1],
    )
    owner_pid = None
    try:
        child.stdin.write((json.dumps({"credential": credential}) + "\n").encode())
        await child.stdin.drain()
        ready = await asyncio.wait_for(child.stdout.readline(), timeout=10)
        assert ready.strip().isdigit(), "Agent fixture did not start"
        owner_pid = int(ready.strip())
        reached = await asyncio.wait_for(child.stdout.readline(), timeout=15)
        assert reached.strip() == (b"saved" if mode == "save" else b"cleared")
    finally:
        if owner_pid is not None:
            try:
                os.kill(owner_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        elif child.returncode is None:
            child.kill()
        child.stdin.close()
        await asyncio.wait_for(child.wait(), timeout=10)
    assert child.returncode != 0


async def verify_real_keyring_rotation(client, enrollment):
    store = secure_keyring()
    service = "NetGuardian-integration-rotation-" + str(uuid4())
    account = str(enrollment.agent_id)
    pending_account = account + ":rotation"
    pending = secrets.token_urlsafe(48)
    try:
        assert store.get_password(service, account) is None
        assert store.get_password(service, pending_account) is None
        store.set_password(service, account, enrollment.credential)
        store.set_password(service, pending_account, pending)
        # Commit server rotation, deliberately do not promote the local credential.
        # This reproduces restart state after a lost acknowledgement, not a dropped socket.
        await control_request(client, "/api/agent/rotate", {"credential": pending})
        assert secrets.compare_digest(store.get_password(service, account), enrollment.credential)
        assert (
            await client.post(
                "/api/agent/poll", headers={"Authorization": f"Bearer {enrollment.credential}"}
            )
        ).status_code == 401
        recovered_store = secure_keyring()
        recovered = await rotate_credential(
            client,
            recovered_store,
            service,
            account,
            recovered_store.get_password(service, account),
        )
        assert secrets.compare_digest(recovered, pending)
        assert secrets.compare_digest(recovered_store.get_password(service, account), pending)
        assert recovered_store.get_password(service, pending_account) is None
        assert (await control_request(client, "/api/agent/poll"))["job"] is None
    finally:
        for name in (account, pending_account):
            if store.get_password(service, name) is not None:
                store.delete_password(service, name)
    assert store.get_password(service, account) is None
    assert store.get_password(service, pending_account) is None


@pytest.mark.parametrize("storage", ["sqlite", "postgres"])
def test_https_agent_incident_report_and_spool_replay(tmp_path, monkeypatch, request, storage):
    tenant = "one" if storage == "sqlite" else "workflow-" + str(uuid4())
    database_url = f"sqlite:///{tmp_path / 'workflow.db'}"
    if storage == "postgres":
        engine, _ = request.getfixturevalue("postgres")
        database_url = engine.url.render_as_string(hide_password=False)

    async def scenario():
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        port = listener.getsockname()[1]
        origin = f"https://netguardian.test:{port}"
        target = origin + "/fixture"
        settings = Settings(
            database_url,
            {"a" * 32: tenant},
            {tenant: CloudPolicy("fixture", frozenset({("netguardian.test", port, "https")}))},
        )
        upgrade(settings.database_url)
        app = create_app(settings)
        target_status = 503
        observations = []

        @app.head("/fixture")
        def fixture():
            observations.append(target_status)
            return Response(status_code=target_status)

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                ssl_certfile=str(FIXTURES / "server.crt"),
                ssl_keyfile=str(FIXTURES / "server.key"),
                log_level="error",
                access_log=False,
                timeout_graceful_shutdown=2,
            )
        )
        context = ssl.create_default_context(cafile=str(FIXTURES / "server.crt"))
        real_getaddrinfo = socket.getaddrinfo

        def fixture_address(host, *args, **kwargs):
            if host in ("netguardian.test", b"netguardian.test"):
                host = "127.0.0.1"
            return real_getaddrinfo(host, *args, **kwargs)

        async def fixture_dns(host, *, evidence=None):
            assert host == "netguardian.test"
            return ("127.0.0.1",)

        def authorize_fixture(self, address):
            if address != "127.0.0.1":
                raise PolicyDenied("Only loopback fixture is authorized")
            return address

        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(5):
                while not server.started:
                    if task.done():
                        await task
                        raise AssertionError("HTTPS API did not start")
                    await asyncio.sleep(0.01)
            with monkeypatch.context() as patch:
                patch.setattr(socket, "getaddrinfo", fixture_address)
                patch.setattr("probe_core.executor.resolve_public", fixture_dns)
                patch.setattr("probe_core.executor.ssl.create_default_context", lambda: context)
                patch.setattr(LocalPolicy, "validate_address", authorize_fixture)
                patch.setattr(CloudPolicy, "validate_address", authorize_fixture)
                async with httpx.AsyncClient(
                    base_url=origin,
                    verify=context,
                    trust_env=False,
                    timeout=5,
                    follow_redirects=False,
                ) as client:
                    admin = {"Authorization": "Bearer " + "a" * 32}
                    response = await client.post(
                        "/api/agents/enrollment",
                        headers=admin,
                        json={"name": "HTTPS integration fixture"},
                    )
                    assert response.status_code == 201
                    enrollment = EnrollmentResponse.model_validate(
                        await control_request(
                            client, "/api/agent/enroll", {"token": response.json()["token"]}
                        )
                    )
                    client.headers["Authorization"] = f"Bearer {enrollment.credential}"
                    config = AgentConfig(
                        api_url=origin, agent_id=enrollment.agent_id, origins=[origin]
                    )
                    config.validate_server()
                    response = await client.post(
                        "/api/monitors",
                        headers=admin,
                        json={
                            "name": "Fixture availability",
                            "target": target,
                            "kind": "http",
                            "agent_id": str(enrollment.agent_id),
                            "open_after": 1,
                            "recover_after": 1,
                        },
                    )
                    assert response.status_code == 201
                    monitor_id = response.json()["id"]
                    evidence_ids = []
                    spool_path = tmp_path / "private-spool" / "pending.json"
                    binding = f"{origin}:{enrollment.agent_id}"
                    for status in (503, 204):
                        target_status = status
                        # Advance the schedule explicitly instead of waiting a minute.
                        with app.state.sessions.begin() as session:
                            session.get(Monitor, monitor_id).next_due = datetime.now(UTC)
                        tick(app.state.sessions, settings.policies)
                        assignment = await control_request(client, "/api/agent/poll")
                        upload = await process_assignment(config, assignment)
                        result = upload["measurement"]
                        assert result["status"] == "success" and result["http_status"] == status
                        assert result["tls"]["hostname_verified"] is True
                        assert result["timings"]["http_total_ms"] > 0
                        evidence_ids.append(result["job_id"])
                        # Persist real measured evidence in another process, then kill it.
                        restored = await persist_then_kill(spool_path, binding, upload)
                        assert await control_request(client, "/api/agent/results", restored) == {
                            "accepted": True,
                            "duplicate": False,
                        }
                        assert await control_request(client, "/api/agent/results", restored) == {
                            "accepted": True,
                            "duplicate": True,
                        }
                        ResultSpool(spool_path, binding).clear()
                        tick(app.state.sessions, settings.policies)
                    incidents = (await client.get("/api/incidents", headers=admin)).json()
                    assert len(incidents) == 1 and incidents[0]["state"] == "recovered"
                    response = await client.post(
                        "/api/reports", headers=admin, json={"incident_id": incidents[0]["id"]}
                    )
                    assert response.status_code == 201
                    report_id = response.json()["id"]
                    report = (await client.get(f"/api/reports/{report_id}", headers=admin)).json()
                    assert report["integrity"] == "verified"
                    assert [e["job_id"] for e in report["snapshot"]["evidence"]] == evidence_ids
                    response = await client.post(
                        "/api/diagnostic-pairs",
                        headers=admin,
                        json={
                            "target": target,
                            "kind": "http",
                            "agent_id": str(enrollment.agent_id),
                        },
                    )
                    assert response.status_code == 202
                    pair = response.json()
                    comparison_request = {
                        "left_job_id": pair["cloud_job_id"],
                        "right_job_id": pair["agent_job_id"],
                    }
                    assert (
                        await client.post(
                            "/api/comparisons", headers=admin, json=comparison_request
                        )
                    ).status_code == 409
                    assert await run_once(app.state.sessions, settings.policies, vantage_id=uuid4())
                    assignment = await control_request(client, "/api/agent/poll")
                    assert assignment["job"]["job_id"] == pair["agent_job_id"]
                    paired_upload = await process_assignment(config, assignment)
                    await control_request(client, "/api/agent/results", paired_upload)
                    response = await client.post(
                        "/api/comparisons", headers=admin, json=comparison_request
                    )
                    assert response.status_code == 200
                    comparison = response.json()
                    assert comparison["comparable"] is True
                    assert comparison["evidence_ids"] == [
                        pair["cloud_job_id"],
                        pair["agent_job_id"],
                    ]
                    assert "http_total_ms" in comparison["right_minus_left_ms"]
                    assert "dns_lookup_ms" not in comparison["right_minus_left_ms"]
                    assert comparison["skew_seconds"] <= 30
                    assert observations == [503, 204, 204, 204]
                    assert not spool_path.exists()
                    # Run the real Agent main loop in two separate processes. The first
                    # is killed after durable save, the second after accepted upload/clear.
                    process_spool = tmp_path / "process-spool" / "pending.json"
                    process_config = config.model_copy(update={"spool_path": process_spool})
                    config_path = tmp_path / "process-config.json"
                    config_path.write_text(process_config.model_dump_json(), encoding="utf-8")
                    response = await client.post(
                        "/api/jobs",
                        headers=admin,
                        json={
                            "kind": "http",
                            "target": target,
                            "agent_id": str(enrollment.agent_id),
                        },
                    )
                    assert response.status_code == 202
                    process_job = response.json()["id"]
                    await run_agent_until_killed(config_path, enrollment.credential, "save")
                    restored = ResultSpool(
                        process_spool, f"NetGuardian:{origin}:{enrollment.agent_id}"
                    ).load()
                    assert restored["measurement"]["job_id"] == process_job
                    assert restored["measurement"]["http_status"] == 204
                    assert observations == [503, 204, 204, 204, 204]
                    await run_agent_until_killed(config_path, enrollment.credential, "clear")
                    assert not process_spool.exists()
                    assert observations == [503, 204, 204, 204, 204]  # No second probe.
                    delivered = await client.get(f"/api/jobs/{process_job}", headers=admin)
                    assert delivered.status_code == 200
                    saved_result = delivered.json()["result"]
                    assert saved_result["received_at"] is not None
                    assert {**saved_result, "received_at": None} == restored["measurement"]
                    if os.environ.get("NETGUARDIAN_TEST_KEYRING") == "true":
                        await verify_real_keyring_rotation(client, enrollment)
                        response = await client.delete(
                            f"/api/agents/{enrollment.agent_id}", headers=admin
                        )
                        assert response.status_code == 204
                        assert (await client.post("/api/agent/poll")).status_code == 401
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)
            listener.close()

    asyncio.run(scenario())
