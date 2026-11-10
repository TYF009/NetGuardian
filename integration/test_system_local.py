"""Opt-in real OS tools against loopback only; never external destinations."""

import asyncio
import os
import sys

import pytest

from probe_core.contracts import SystemProbeDetails
from probe_core.system_tools import system_probe


@pytest.mark.skipif(
    os.environ.get("NETGUARDIAN_TEST_SYSTEM_PROBES") != "true",
    reason="Explicit local system-probe integration opt-in required",
)
@pytest.mark.skipif(sys.platform != "win32", reason="Windows integration fixture")
@pytest.mark.parametrize("address", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("kind", ["icmp", "traceroute"])
def test_windows_loopback_probe(kind, address):
    result = SystemProbeDetails.model_validate(asyncio.run(system_probe(kind, address)))
    assert result.destination_reached
    if kind == "icmp":
        assert result.sent == result.received == 1
        assert len(result.rtt_samples) == 1
    else:
        assert len(result.hops) == 1
        assert address in [str(value) for value in result.hops[0].addresses]
