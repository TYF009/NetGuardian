"""Real UDP resolver exchanges; only the resolver endpoint is test-configured."""

import asyncio
from uuid import uuid4

import dns.asyncresolver
import dns.message
import dns.rcode
import dns.rdatatype
import dns.rrset
import pytest

from probe_core.contracts import ProbeRequest
from probe_core.executor import execute_probe
from probe_core.policy import CloudPolicy


@pytest.mark.parametrize("case", ["answers", "nxdomain", "mixed_private"])
def test_dns_wire_evidence_and_policy(monkeypatch, case):
    async def scenario():
        received = []

        class ResolverFixture(asyncio.DatagramProtocol):
            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, address):
                query = dns.message.from_wire(data)
                question = query.question[0]
                name = str(question.name)
                record_type = dns.rdatatype.to_text(question.rdtype)
                received.append((name, record_type))
                response = dns.message.make_response(query)
                if case == "nxdomain":
                    response.set_rcode(dns.rcode.NXDOMAIN)
                else:
                    response.answer.append(
                        dns.rrset.from_text(name, 120, "IN", "CNAME", "canonical.netguardian.test.")
                    )
                    values = ["8.8.8.8"] if record_type == "A" else ["2606:4700:4700::1111"]
                    if case == "mixed_private" and record_type == "A":
                        values.append("127.0.0.1")
                    response.answer.append(
                        dns.rrset.from_text(
                            "canonical.netguardian.test.", 60, "IN", record_type, *values
                        )
                    )
                self.transport.sendto(response.to_wire(), address)

        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            ResolverFixture, local_addr=("127.0.0.1", 0)
        )
        port = transport.get_extra_info("sockname")[1]
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = ["127.0.0.1"]
        resolver.port = port
        resolver.cache = None
        try:
            with monkeypatch.context() as patch:
                patch.setattr("probe_core.executor.dns.asyncresolver.Resolver", lambda: resolver)
                policy = CloudPolicy("fixture", frozenset({("netguardian.test", 443, "https")}))
                result = await execute_probe(
                    ProbeRequest(
                        job_id=uuid4(),
                        kind="dns",
                        target="https://netguardian.test",
                        policy_version="fixture",
                    ),
                    policy,
                    uuid4(),
                )
            assert result.connected_ip is None  # DNS-only: never contact returned public IPs.
            if case == "nxdomain":
                assert result.status == "error"
                assert result.error.code == "resolution_failed"
                assert received == [("netguardian.test.", "A")]
            else:
                assert received == [("netguardian.test.", "A"), ("netguardian.test.", "AAAA")]
                assert result.dns.used_dns
                assert [answer.record_type for answer in result.dns.answers] == ["A", "AAAA"]
                for answer in result.dns.answers:
                    assert answer.ttl_seconds == 60
                    assert answer.canonical_name == "canonical.netguardian.test."
                    assert answer.resolver == "127.0.0.1"
                    assert answer.resolver_port == port
                if case == "mixed_private":
                    assert result.status == "denied"
                    assert result.error.code == "policy_denied"
                else:
                    assert result.status == "success"
                    assert set(map(str, result.resolved_ips)) == {"8.8.8.8", "2606:4700:4700::1111"}
                    assert result.timings.dns_lookup_ms > 0
        finally:
            transport.close()
            await asyncio.sleep(0)

    asyncio.run(scenario())
