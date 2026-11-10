"""Exercise restart delivery through the real Agent loop, with offline transport."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from agent.client import AgentConfig, run_locked
from agent.spool import ResultSpool
from probe_core.contracts import Measurement


@pytest.mark.parametrize(
    "status,body,retained,unauthorized",
    [
        (200, {"accepted": True, "duplicate": False}, False, False),
        (200, {"accepted": True, "duplicate": True}, False, False),
        (200, {"accepted": False, "duplicate": False}, True, False),
        (200, {"accepted": True, "duplicate": "false"}, True, False),
        (503, {}, True, False),
        (401, {}, True, True),
        (403, {}, True, True),
        (404, {}, False, False),
        (409, {}, False, False),
        (422, {}, False, False),
    ],
)
def test_restart_delivers_before_poll_and_clears_only_terminal_result(
    tmp_path, monkeypatch, status, body, retained, unauthorized
):
    config = AgentConfig(
        api_url="https://control.example.com",
        agent_id=uuid4(),
        spool_path=tmp_path / "private" / "pending.json",
    )
    measurement = Measurement(
        job_id=uuid4(),
        attempt=1,
        kind="dns",
        vantage_id=config.agent_id,
        target="https://example.com",
        configuration_hash="a" * 64,
        observed_at=datetime.now(UTC),
        probe_version="test",
        policy_version="v1",
        status="success",
    )
    upload = {"lease_token": str(uuid4()), "measurement": measurement.model_dump(mode="json")}
    spool = ResultSpool(config.spool_path, f"NetGuardian:{config.api_url}:{config.agent_id}")
    spool.save(upload)

    class Store:
        def get_password(self, service, account):
            return None if account.endswith(":rotation") else "test-only-credential"

    seen = []

    class ResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield json.dumps(body).encode()

    def handler(request):
        assert request.url.path == "/api/agent/results", "Restart must not poll or re-probe"
        assert request.headers["Authorization"] == "Bearer test-only-credential"
        seen.append(json.loads(request.content))
        return httpx.Response(status, stream=ResponseStream())

    real_client = httpx.AsyncClient
    monkeypatch.setattr("agent.client.secure_keyring", Store)
    monkeypatch.setattr(
        "agent.client.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def stop_after_iteration(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr("agent.client.asyncio.sleep", stop_after_iteration)

    async def scenario():
        error = RuntimeError if unauthorized else asyncio.CancelledError
        with pytest.raises(error):
            await run_locked(tmp_path / "config.json", config, False, False)

    asyncio.run(scenario())
    assert seen == [upload]
    assert spool.load() == (upload if retained else None)
