"""Platform fixtures are synthetic command output, not live measurements."""

import asyncio

import pytest

from probe_core.system_tools import command_for, parse_output, system_probe


def test_fixed_arguments_and_injection_rejection():
    for platform in ("win32", "linux"):
        for kind in ("icmp", "traceroute"):
            args = command_for(kind, "8.8.8.8", platform)
            assert args[-1] == "8.8.8.8"
            assert "15" in args if kind == "traceroute" else "1" in args
            with pytest.raises(ValueError):
                command_for(kind, "8.8.8.8 & whoami", platform)


def test_ping_samples_preserve_upper_bound():
    windows = parse_output("icmp", "Reply from 8.8.8.8: bytes=32 time<1ms TTL=55", "8.8.8.8")
    assert windows["rtt_samples"] == [{"milliseconds": 1.0, "upper_bound": True}]
    linux = parse_output("icmp", "64 bytes from 8.8.8.8: icmp_seq=1 ttl=55 time=2.45 ms", "8.8.8.8")
    assert linux["rtt_samples"][0]["milliseconds"] == 2.45


def test_route_preserves_missing_hops_and_ipv6():
    text = (
        " 1  <1 ms  1 ms  1 ms  192.168.1.1\n"
        " 2  * * * Request timed out.\n"
        " 3  3 ms  4 ms  5 ms  2606:4700:4700::1111"
    )
    route = parse_output("traceroute", text, "2606:4700:4700::1111")
    assert len(route["hops"]) == 3
    assert route["hops"][1]["missing_replies"] == 3
    assert route["destination_reached"]


def test_permission_error_is_explicit(monkeypatch):
    async def denied(args):
        return 1, "Operation not permitted"

    monkeypatch.setattr("probe_core.system_tools.run_bounded", denied)
    with pytest.raises(PermissionError):
        asyncio.run(system_probe("icmp", "8.8.8.8"))
