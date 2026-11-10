"""Real loopback TLS handshakes through the probe transport; no external targets."""

import asyncio
import hashlib
import ssl
from pathlib import Path
from uuid import uuid4

import pytest

from probe_core.contracts import ProbeRequest
from probe_core.executor import execute_probe
from probe_core.policy import CloudPolicy, PolicyDenied

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tls"


class LoopbackFixturePolicy(CloudPolicy):
    def validate_address(self, address):
        # Test-only authorization; production CloudPolicy still denies loopback.
        if address not in {"127.0.0.1", "::1"}:
            raise PolicyDenied("Only the local fixture is allowed")
        return address


@pytest.mark.parametrize("address", ["127.0.0.1", "::1"])
@pytest.mark.parametrize(
    "hostname,trusted,success",
    [
        ("netguardian.test", True, True),
        ("wrong.test", True, False),
        ("netguardian.test", False, False),
    ],
)
def test_real_tls_verification(monkeypatch, hostname, trusted, success, address):
    async def scenario():
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(FIXTURES / "server.crt", FIXTURES / "server.key")
        original_context = ssl.create_default_context
        context = (
            original_context(cafile=str(FIXTURES / "server.crt")) if trusted else original_context()
        )
        requests = []
        handlers = set()

        async def serve(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                async with asyncio.timeout(2):
                    requests.append(await reader.readuntil(b"\r\n\r\n"))
                    writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
                    await writer.drain()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, ssl.SSLError):
                    pass
                handlers.discard(task)

        server = await asyncio.start_server(serve, address, 0, ssl=server_context)
        port = server.sockets[0].getsockname()[1]

        async def resolve(host, *, evidence=None):
            assert host == hostname
            return (address,)

        try:
            with monkeypatch.context() as patch:
                patch.setattr("probe_core.executor.resolve_public", resolve)
                patch.setattr("probe_core.executor.ssl.create_default_context", lambda: context)
                policy = LoopbackFixturePolicy("fixture", frozenset({(hostname, port, "https")}))
                request = ProbeRequest(
                    job_id=uuid4(),
                    kind="http",
                    target=f"https://{hostname}:{port}",
                    policy_version="fixture",
                )
                result = await execute_probe(request, policy, uuid4())
            assert str(result.connected_ip) == address
            assert result.timings.tcp_connect_ms is not None
            if success:
                assert result.status == "success" and result.http_status == 204
                assert result.tls is not None and result.tls.hostname_verified
                der = ssl.PEM_cert_to_DER_cert((FIXTURES / "server.crt").read_text())
                assert result.tls.leaf_sha256 == hashlib.sha256(der).hexdigest()
                assert result.timings.tls_handshake_ms is not None
                assert requests[0].startswith(b"HEAD / HTTP/1.1")
            else:
                assert result.status == "error"
                assert result.error.code == "tls_verification_failed"
                assert result.error.tls_verify_code is not None
                assert result.tls is None and result.http_status is None
                assert requests == []
        finally:
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.gather(*handlers)

    asyncio.run(scenario())
