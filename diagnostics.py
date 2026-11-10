"""Fail-closed legacy probe boundary pending approved target policies."""

from dataclasses import dataclass

DISABLED_REASON = (
    "Temporarily disabled pending target authorization, SSRF protection, "
    "execution limits and safe platform adapters."
)


@dataclass(frozen=True)
class ProbeResult:
    status: str = "disabled"
    http_request_ms: float | None = None
    reason: str = DISABLED_REASON


def probe_disabled(*args: object, **kwargs: object) -> ProbeResult:
    """Reject every target without DNS, sockets, HTTP or subprocess execution."""
    return ProbeResult()


# Retain legacy entry points as fail-closed compatibility stubs.
get_ping_latency = probe_disabled
get_http_request_duration = probe_disabled
check_http_status = probe_disabled
check_port = probe_disabled
get_dns_info = probe_disabled
run_traceroute = probe_disabled
get_public_ip = probe_disabled
get_ip_info = probe_disabled
get_local_info = probe_disabled


def format_http_duration(result: ProbeResult) -> str:
    """Never turn unavailable measurements into zero or timeouts."""
    if result.status != "success" or result.http_request_ms is None:
        return result.status.capitalize()
    return f"{result.http_request_ms:.2f} ms"
