"""Executor tests use controlled async doubles; no Internet traffic."""

import asyncio
from uuid import uuid4

from probe_core.contracts import ProbeRequest
from probe_core.executor import execute_probe
from probe_core.policy import CloudPolicy

POLICY = CloudPolicy("v1", frozenset({("example.com", 443, "https")}))


def request(kind="dns", target="https://example.com"):
    return ProbeRequest(job_id=uuid4(), kind=kind, target=target, policy_version="v1")


def test_denied_before_resolution(monkeypatch):
    async def forbidden(host, *, evidence=None):
        raise AssertionError("Unauthorized name reached resolver")

    monkeypatch.setattr("probe_core.executor.resolve_public", forbidden)
    result = asyncio.run(execute_probe(request(target="https://evil.test"), POLICY, uuid4()))
    assert result.status == "denied"
    assert not result.resolved_ips


def test_dns_success_and_mixed_answer_denial(monkeypatch):
    async def public(host, *, evidence=None):
        return ("8.8.8.8",)

    monkeypatch.setattr("probe_core.executor.resolve_public", public)
    result = asyncio.run(execute_probe(request(), POLICY, uuid4()))
    assert result.status == "success"
    assert result.timings.dns_lookup_ms >= 0
    assert result.connected_ip is None

    async def mixed(host, *, evidence=None):
        return ("8.8.8.8", "127.0.0.1")

    monkeypatch.setattr("probe_core.executor.resolve_public", mixed)
    result = asyncio.run(execute_probe(request("http"), POLICY, uuid4()))
    assert result.status == "denied"
    assert result.connected_ip is None


def test_dns_deadline(monkeypatch):
    async def slow(host, *, evidence=None):
        await asyncio.sleep(1)
        return ("8.8.8.8",)

    monkeypatch.setattr("probe_core.executor.resolve_public", slow)
    limited = request().model_copy(update={"deadline_ms": 10})
    result = asyncio.run(execute_probe(limited, POLICY, uuid4()))
    assert result.status == "timeout"


def test_unsupported_capability():
    result = asyncio.run(execute_probe(request("icmp"), POLICY, uuid4()))
    assert result.status == "unsupported"


def test_pinned_http_transport_and_tls_verification(monkeypatch):
    import ssl

    async def scenario(headers, tls_error=False):
        class Socket:
            closed = False

            def setblocking(self, value):
                pass

            def getpeername(self):
                return ("8.8.8.8", 443)

            def close(self):
                self.closed = True

        class TlsSession:
            def getpeercert(self, binary_form=False):
                if binary_form:
                    return b"synthetic-certificate-fixture"
                return {
                    "notBefore": "Jan  1 00:00:00 2026 GMT",
                    "notAfter": "Jan  1 00:00:00 2027 GMT",
                }

            def cipher(self):
                return ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

            def version(self):
                return "TLSv1.3"

        class Writer:
            payload = b""
            closed = False

            def get_extra_info(self, name):
                assert name == "ssl_object"
                return TlsSession()

            def write(self, data):
                self.payload += data

            async def drain(self):
                pass

            def close(self):
                self.closed = True

        class Reader:
            async def readexactly(self, count):
                assert count == 1
                return headers[:1]

            async def readuntil(self, separator):
                assert separator == b"\r\n\r\n"
                return headers[1:]

        sock, writer = Socket(), Writer()
        connections = []

        async def resolve(host, *, evidence=None):
            assert host == "example.com"
            return ("8.8.8.8",)

        async def connect(actual_socket, address):
            assert actual_socket is sock
            connections.append(address)

        async def open_stream(**kwargs):
            assert kwargs["sock"] is sock
            assert kwargs["server_hostname"] == "example.com"
            assert kwargs["ssl"].check_hostname is True
            assert kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED
            if tls_error:
                raise ssl.SSLCertVerificationError("Test certificate rejected")
            return Reader(), writer

        with monkeypatch.context() as patch:
            patch.setattr("probe_core.executor.resolve_public", resolve)
            patch.setattr("probe_core.executor.socket.socket", lambda *args: sock)
            patch.setattr(asyncio.get_running_loop(), "sock_connect", connect)
            patch.setattr("probe_core.executor.asyncio.open_connection", open_stream)
            result = await execute_probe(
                request("http", "https://example.com/a?x=1"), POLICY, uuid4()
            )
        assert connections == [("8.8.8.8", 443)]
        assert writer.closed or sock.closed
        return result, writer

    result, writer = asyncio.run(
        scenario(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1\r\n\r\n")
    )
    assert result.status == "success" and result.http_status == 302
    assert b"HEAD /a?x=1 HTTP/1.1" in writer.payload
    assert result.timings.tls_handshake_ms is not None
    assert result.tls.protocol == "TLSv1.3"
    assert result.tls.cipher_bits == 256
    assert result.tls.not_after.year == 2027
    assert result.tls.hostname_verified is True
    result, _ = asyncio.run(scenario(b"HTTP/1.1 200 OK\r\nX: " + b"a" * 17000 + b"\r\n\r\n"))
    assert result.status == "error"
    result, _ = asyncio.run(scenario(b"HTTP/1.1 200 OK\r\n\r\n", tls_error=True))
    assert result.status == "error"

    assert result.tls is None  # Certificate verification failed before recording evidence.
    assert result.error.code == "tls_verification_failed"
    assert result.error.tls_verify_code is None  # Synthetic exception has no runtime code.


def test_dns_duration_uses_high_resolution_monotonic_clock(monkeypatch):
    from types import SimpleNamespace

    import pytest

    async def resolve(host, *, evidence=None):
        return ("8.8.8.8",)

    samples = iter((10.0, 10.001, 10.0015))
    monkeypatch.setattr(
        "probe_core.executor.time", SimpleNamespace(perf_counter=lambda: next(samples))
    )
    monkeypatch.setattr("probe_core.executor.resolve_public", resolve)
    result = asyncio.run(execute_probe(request(), POLICY, uuid4()))
    assert result.status == "success"
    assert result.timings.dns_lookup_ms == pytest.approx(0.5)
    assert result.probe_version == "0.2.1"
