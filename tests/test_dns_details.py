"""DNS details come from actual resolver answers, without invented metadata."""

import asyncio
from types import SimpleNamespace

from probe_core.executor import resolve_public


def test_answer_metadata_and_literal_bypass(monkeypatch):
    class Answer:
        rrset = SimpleNamespace(ttl=120)
        canonical_name = "canonical.example."
        nameserver = "192.0.2.53"
        port = 53

        def __init__(self, values):
            self.values = values

        def __iter__(self):
            return iter(self.values)

    class Resolver:
        async def resolve(self, host, record_type, **kwargs):
            assert kwargs == {"lifetime": 3, "search": False}
            return Answer(["8.8.8.8"] if record_type == "A" else ["2606:4700:4700::1111"])

    monkeypatch.setattr("probe_core.executor.dns.asyncresolver.Resolver", Resolver)
    evidence = []
    addresses = asyncio.run(resolve_public("example.com", evidence=evidence))
    assert len(addresses) == 2
    assert [item["record_type"] for item in evidence] == ["A", "AAAA"]
    assert evidence[0]["ttl_seconds"] == 120
    assert evidence[0]["resolver"] == "192.0.2.53"
    literal_evidence = []
    assert asyncio.run(resolve_public("8.8.8.8", evidence=literal_evidence)) == ("8.8.8.8",)
    assert literal_evidence == []


def test_literal_measurement_has_no_dns_timing():
    from uuid import uuid4

    from probe_core.contracts import ProbeRequest
    from probe_core.executor import execute_probe
    from probe_core.policy import CloudPolicy

    policy = CloudPolicy("v1", frozenset({("8.8.8.8", 443, "https")}))
    request = ProbeRequest(
        job_id=uuid4(), kind="dns", target="https://8.8.8.8", policy_version="v1"
    )
    result = asyncio.run(execute_probe(request, policy, uuid4()))
    assert result.status == "success"
    assert result.dns.used_dns is False
    assert result.dns.answers == ()
    assert result.timings.dns_lookup_ms is None
