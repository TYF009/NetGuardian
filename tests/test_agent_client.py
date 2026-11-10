"""Local agent authorization is independent of server-issued jobs."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from agent.client import AgentConfig, control_request, process_assignment
from agent.policy import LocalPolicy
from probe_core.policy import PolicyDenied, plan_connection


def test_local_private_scope_is_explicit():
    origin = frozenset({("192.168.1.10", 443, "https")})
    policy = LocalPolicy("v1", origin, private_cidrs=("192.168.1.0/24",))
    assert plan_connection(policy, "https://192.168.1.10", ("192.168.1.10",)).addresses
    for address in ("192.168.2.10", "127.0.0.1", "169.254.169.254", "::1"):
        with pytest.raises(PolicyDenied):
            policy.validate_address(address)
    with pytest.raises(ValueError):
        LocalPolicy("v1", origin, private_cidrs=("0.0.0.0/0",))  # noqa: S104


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://example.com/path",
        "https://example.com?token=x",
    ],
)
def test_agent_requires_https_origin(url):
    with pytest.raises(ValueError):
        AgentConfig(api_url=url).validate_server()


def test_cloud_cannot_expand_local_policy():
    config = AgentConfig(api_url="https://control.example.com", agent_id=uuid4(), origins=[])
    assignment = {
        "job": {
            "job_id": str(uuid4()),
            "kind": "http",
            "target": "https://example.com",
            "policy_version": "cloud-v1",
        },
        "lease_token": str(uuid4()),
        "attempt": 2,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
    }
    result = asyncio.run(process_assignment(config, assignment))
    assert result["measurement"]["status"] == "denied"
    assert result["measurement"]["attempt"] == 2
    assignment["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        asyncio.run(process_assignment(config, assignment))


@pytest.mark.parametrize(
    "body,encoding,accepted",
    [
        (b'{"job":null}', "identity", True),
        (b"x" * 65537, "identity", False),
        (b"[]", "identity", False),
        (b"invalid", "identity", False),
        (b"compressed", "gzip", False),
    ],
)
def test_control_response_is_bounded_and_validated(body, encoding, accepted):
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0, len(body), 1024):
                yield body[offset : offset + 1024]

    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"content-encoding": encoding}, stream=Chunks())

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://control.example.com", transport=httpx.MockTransport(handler)
        ) as client:
            if accepted:
                assert await control_request(client, "/api/agent/poll") == {"job": None}
            else:
                with pytest.raises(ValueError):
                    await control_request(client, "/api/agent/poll")

    asyncio.run(scenario())


def test_control_auth_failure_does_not_read_error_body():
    class Unreadable(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Unauthorized response body must not be consumed")
            yield b""  # pragma: no cover

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://control.example.com",
            transport=httpx.MockTransport(lambda request: httpx.Response(401, stream=Unreadable())),
        ) as client:
            with pytest.raises(httpx.HTTPStatusError) as error:
                await control_request(client, "/api/agent/poll")
            assert error.value.response.status_code == 401

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [{}, {"accepted": False, "duplicate": False}, {"accepted": True, "duplicate": "false"}],
)
def test_incomplete_acknowledgement_is_not_delivery(payload):
    from agent.client import UploadAcknowledgement

    with pytest.raises(ValueError):
        UploadAcknowledgement.model_validate(payload)


def test_enrollment_response_rejects_invalid_credentials():
    from agent.client import EnrollmentResponse

    for credential in ("short", "x" * 129, "contains whitespace " * 3):
        with pytest.raises(ValueError):
            EnrollmentResponse.model_validate({"agent_id": str(uuid4()), "credential": credential})


def test_plaintext_keyring_backend_is_rejected(monkeypatch):
    from agent.client import secure_keyring

    class PlaintextBackend:
        pass

    monkeypatch.setattr("agent.client.keyring.get_keyring", PlaintextBackend)
    with pytest.raises(RuntimeError):
        secure_keyring()


def test_rotation_recovers_when_server_already_changed(monkeypatch):
    from agent.client import rotate_credential

    class Store:
        values = {"agent": "old-credential", "agent:rotation": "pending-credential"}

        def get_password(self, service, account):
            return self.values.get(account)

        def set_password(self, service, account, value):
            self.values[account] = value

        def delete_password(self, service, account):
            del self.values[account]

    attempts = []

    async def request(client, path, payload):
        attempts.append(client.headers["Authorization"])
        if len(attempts) == 1:
            response = httpx.Response(
                401, request=httpx.Request("POST", "https://control.example.com")
            )
            response.raise_for_status()
        return {"rotated": True}

    monkeypatch.setattr("agent.client.control_request", request)

    async def scenario():
        store = Store()
        async with httpx.AsyncClient() as client:
            value = await rotate_credential(client, store, "service", "agent", "old-credential")
        assert value == "pending-credential"
        assert store.values == {"agent": "pending-credential"}
        assert attempts == ["Bearer old-credential", "Bearer pending-credential"]

    asyncio.run(scenario())
