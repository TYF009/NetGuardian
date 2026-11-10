"""Bounded DNS/TCP/TLS/HTTP HEAD probes with numeric-address connection pinning."""

import asyncio
import hashlib
import ipaddress
import os
import socket
import ssl
import time
from datetime import UTC, datetime
from uuid import UUID

import dns.asyncresolver
import dns.exception
import dns.resolver

from probe_core.contracts import Measurement, ProbeError, ProbeRequest, Timings, configuration_hash
from probe_core.policy import CloudPolicy, PolicyDenied, plan_connection
from probe_core.system_tools import system_probe


async def resolve_public(host: str, *, evidence=None) -> tuple[str, ...]:
    """Resolve both families; fail closed on partial resolver errors."""
    try:
        return (str(ipaddress.ip_address(host)),)
    except ValueError:
        pass
    resolver = dns.asyncresolver.Resolver()
    addresses = []
    for record_type in ("A", "AAAA"):
        try:
            answers = await resolver.resolve(host, record_type, lifetime=3, search=False)
            values = tuple(str(answer) for answer in answers)
            if len(addresses) + len(values) > 16:
                raise ValueError("DNS address count exceeds limit")
            addresses.extend(values)
            if evidence is not None:
                evidence.append(
                    {
                        "record_type": record_type,
                        "addresses": values,
                        "ttl_seconds": answers.rrset.ttl,
                        "canonical_name": str(answers.canonical_name),
                        "resolver": answers.nameserver,
                        "resolver_port": answers.port,
                    }
                )
        except dns.resolver.NoAnswer:
            continue
    return tuple(addresses)


async def execute_probe(
    request: ProbeRequest, policy: CloudPolicy, vantage_id: UUID
) -> Measurement:
    """No proxy, automatic redirects, shell execution, credentials or body download."""
    base = dict(
        job_id=request.job_id,
        attempt=1,
        kind=request.kind,
        vantage_id=vantage_id,
        target=request.target,
        configuration_hash=configuration_hash(request),
        observed_at=datetime.now(UTC),
        probe_version="0.2.1",
        policy_version=policy.version,
    )
    timings = {}
    addresses = ()
    connected = None
    http_status = None
    system_details = None
    tls_details = None
    dns_details = None
    writer = None
    sock = None
    status = "success"
    error = None
    started = time.perf_counter()
    try:
        async with asyncio.timeout(request.deadline_ms / 1000):
            if request.policy_version != policy.version:
                raise PolicyDenied("Policy version changed")
            target = policy.authorize(request.target)
            if (
                request.kind in {"icmp", "traceroute"}
                and os.environ.get("NETGUARDIAN_ENABLE_SYSTEM_PROBES") != "true"
            ):
                raise NotImplementedError("Probe capability is not available")
            if request.kind == "tls" and target.scheme != "https":
                raise PolicyDenied("TLS probes require an HTTPS origin")
            before = time.perf_counter()
            dns_evidence = []
            answers = await resolve_public(target.host, evidence=dns_evidence)
            try:
                ipaddress.ip_address(target.host)
                used_dns = False
            except ValueError:
                used_dns = True
            dns_details = {"used_dns": used_dns, "answers": dns_evidence}
            plan = plan_connection(policy, request.target, answers)
            addresses = plan.addresses
            if used_dns:
                timings["dns_lookup_ms"] = (time.perf_counter() - before) * 1000
            if request.kind in {"icmp", "traceroute"}:
                system_details = await system_probe(request.kind, addresses[0])
                samples = system_details["rtt_samples"]
                if request.kind == "icmp" and samples and not samples[0]["upper_bound"]:
                    timings["icmp_rtt_ms"] = samples[0]["milliseconds"]
            if request.kind in {"tcp", "tls", "http"}:
                address = addresses[0]  # One bounded attempt; no hidden fallback or retries.
                family = socket.AF_INET6 if ":" in address else socket.AF_INET
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.setblocking(False)
                before = time.perf_counter()
                endpoint = (
                    (address, target.port, 0, 0)
                    if family == socket.AF_INET6
                    else (address, target.port)
                )
                await asyncio.get_running_loop().sock_connect(sock, endpoint)
                connected = str(ipaddress.ip_address(sock.getpeername()[0]))
                if connected != address:
                    connected = None
                    raise PolicyDenied("Connected peer does not match pinned address")
                timings["tcp_connect_ms"] = (time.perf_counter() - before) * 1000
                if request.kind != "tcp":
                    context = ssl.create_default_context() if target.scheme == "https" else None
                    before = time.perf_counter()
                    reader, writer = await asyncio.open_connection(
                        sock=sock,
                        ssl=context,
                        server_hostname=target.host if context else None,
                        limit=16384,
                    )
                    sock = None  # Writer owns the socket from this point.
                    if context:
                        timings["tls_handshake_ms"] = (time.perf_counter() - before) * 1000
                        connection = writer.get_extra_info("ssl_object")
                        if connection is None:
                            raise ValueError("TLS session details missing")
                        certificate = connection.getpeercert()
                        leaf = connection.getpeercert(binary_form=True)
                        cipher = connection.cipher()
                        if not leaf or not cipher:
                            raise ValueError("TLS peer evidence missing")
                        tls_details = {
                            "protocol": connection.version(),
                            "cipher": cipher[0],
                            "cipher_bits": cipher[2],
                            "leaf_sha256": hashlib.sha256(leaf).hexdigest(),
                            "not_before": datetime.fromtimestamp(
                                ssl.cert_time_to_seconds(certificate["notBefore"]), UTC
                            ),
                            "not_after": datetime.fromtimestamp(
                                ssl.cert_time_to_seconds(certificate["notAfter"]), UTC
                            ),
                            "hostname_verified": True,
                        }
                    if request.kind == "http":
                        host = f"[{target.host}]" if ":" in target.host else target.host
                        host = f"{host}:{target.port}"
                        before = time.perf_counter()
                        writer.write(
                            (
                                f"HEAD {target.path} HTTP/1.1\r\nHost: {host}\r\n"
                                "Connection: close\r\nUser-Agent: NetGuardian/0.2\r\n\r\n"
                            ).encode("ascii")
                        )
                        await writer.drain()
                        first = await reader.readexactly(1)
                        timings["http_ttfb_ms"] = (time.perf_counter() - before) * 1000
                        headers = first + await reader.readuntil(b"\r\n\r\n")
                        if len(headers) > 16384:
                            raise ValueError("HTTP headers exceed limit")
                        line = headers.split(b"\r\n", 1)[0].split(b" ", 2)
                        if len(line) < 2 or line[0] not in {b"HTTP/1.0", b"HTTP/1.1"}:
                            raise ValueError("Invalid HTTP status line")
                        parsed_status = int(line[1])
                        if not 200 <= parsed_status <= 599:
                            raise ValueError("Unsupported HTTP status")
                        http_status = parsed_status
                        timings["http_total_ms"] = (time.perf_counter() - started) * 1000
    except PolicyDenied as exc:
        status, error = "denied", ProbeError(code="policy_denied", message=str(exc))
    except NotImplementedError as exc:
        status, error = "unsupported", ProbeError(code="unsupported", message=str(exc))
    except (TimeoutError, dns.exception.Timeout):
        status, error = "timeout", ProbeError(code="timeout", message="Probe deadline exceeded")
    except dns.exception.DNSException:
        status, error = (
            "error",
            ProbeError(code="resolution_failed", message="DNS resolution failed"),
        )
    except ssl.SSLCertVerificationError as exc:
        status, error = (
            "error",
            ProbeError(
                code="tls_verification_failed",
                message="TLS certificate trust or hostname verification failed",
                tls_verify_code=getattr(exc, "verify_code", None),
            ),
        )
    except PermissionError:
        status, error = (
            "unsupported",
            ProbeError(code="unsupported", message="Insufficient probe permission"),
        )
    except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        status, error = "error", ProbeError(code="transport_error", message="Transport failed")
    finally:
        if writer is not None:
            writer.close()
        if sock is not None:
            sock.close()
    return Measurement(
        **base,
        status=status,
        error=error,
        timings=Timings(**timings),
        resolved_ips=addresses,
        connected_ip=connected,
        http_status=http_status,
        system_probe=system_details,
        tls=tls_details,
        dns=dns_details,
    )
