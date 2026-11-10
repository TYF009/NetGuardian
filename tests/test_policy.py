"""Adversarial fixtures are synthetic inputs, not measured network results."""

import pytest
from pydantic import ValidationError

from probe_core.contracts import ProbeRequest, Timings
from probe_core.policy import (
    CloudPolicy,
    PolicyDenied,
    canonical_host,
    plan_connection,
    public_address,
    redirect_target,
)

POLICY = CloudPolicy("v1", frozenset({("example.com", 443, "https")}))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",  # noqa: S104 - rejection fixture, not a bind address
        "100.64.0.1",
        "224.0.0.1",
        "255.255.255.255",
        "192.0.0.9",
        "192.0.2.1",
        "::",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:8.8.8.8",
        "64:ff9b::808:808",
        "2002:0808:0808::1",
        "2001:db8::1",
        "3fff::1",
        "fe80::1%eth0",
        "2130706433",
        "0177.0.0.1",
        "not-an-ip",
    ],
)
def test_special_addresses_denied(address):
    with pytest.raises(PolicyDenied):
        public_address(address)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://example.com",
        "https://example.com:8443",
        "https://example.com.evil.test",
        "https://user:pass@example.com",
        "https://example.com/#fragment",
        "https://example.com\\@evil.test",
        "https://example.com\n",
        "https://example.com:0",
        "https://example.com:",
        "https://example.com./",
        "https://%65xample.com",
        "https://2130706433",
        "https://0x7f000001",
        "https://127.1",
        "https://example.com;whoami",
    ],
)
def test_unapproved_or_ambiguous_targets_denied(url):
    with pytest.raises(PolicyDenied):
        POLICY.authorize(url)


def test_every_answer_validated_and_rebinding_rejected():
    first = plan_connection(POLICY, "https://example.com/", ("8.8.8.8",))
    assert first.addresses == ("8.8.8.8",)
    assert first.target.host == "example.com"  # Preserve hostname for future SNI/Host.
    for answers in (("127.0.0.1",), ("8.8.8.8", "10.0.0.1"), (), ("8.8.8.8",) * 17):
        with pytest.raises(PolicyDenied):
            plan_connection(POLICY, "https://example.com/", answers)


def test_redirect_requires_independent_authorization_and_new_resolution():
    assert redirect_target(POLICY, "https://example.com/a", "/b", 0) == "https://example.com/b"
    for location, hops in (("//evil.test", 0), ("http://example.com", 0), ("/b", 3)):
        with pytest.raises(PolicyDenied):
            redirect_target(POLICY, "https://example.com", location, hops)


def test_empty_and_revoked_policies_deny():
    for policy in (CloudPolicy("v1"), CloudPolicy("v2", POLICY.allowed_origins, revoked=True)):
        with pytest.raises(PolicyDenied):
            policy.authorize("https://example.com")


def test_canonicalization_and_public_ipv6():
    assert canonical_host("EXAMPLE.COM") == "example.com"
    assert public_address("2606:4700:4700::1111") == "2606:4700:4700::1111"


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan")])
def test_invalid_durations(duration):
    with pytest.raises(ValidationError):
        Timings(http_total_ms=duration)


def test_request_version_and_command_fields_rejected():
    data = dict(
        job_id="00000000-0000-0000-0000-000000000001",
        kind="http",
        target="https://example.com",
        policy_version="v1",
    )
    request = ProbeRequest(**data)
    assert ProbeRequest.model_validate_json(request.model_dump_json()) == request
    for extra in ({"schema_version": "2"}, {"command": "whoami"}, {"deadline_ms": 10001}):
        with pytest.raises(ValidationError):
            ProbeRequest(**data, **extra)


def test_measurement_round_trip_and_semantic_errors():
    from probe_core.contracts import Measurement

    data = dict(
        job_id="00000000-0000-0000-0000-000000000001",
        attempt=1,
        kind="http",
        vantage_id="00000000-0000-0000-0000-000000000002",
        target="https://example.com",
        configuration_hash="a" * 64,
        observed_at="2026-11-04T00:00:00Z",
        probe_version="test",
        policy_version="v1",
        status="success",
        http_status=503,
        timings={"http_total_ms": 0},
    )
    measurement = Measurement(**data)
    assert Measurement.model_validate_json(measurement.model_dump_json()) == measurement
    for changes in (
        {"status": "denied"},
        {"observed_at": "2026-11-04T00:00:00"},
        {"connected_ip": "8.8.8.8"},
        {"kind": "tcp"},
        {"timings": {"icmp_rtt_ms": 10}},
    ):
        with pytest.raises(ValidationError):
            Measurement(**(data | changes))
    denied = Measurement(
        **(
            data
            | {
                "status": "denied",
                "http_status": None,
                "timings": {},
                "error": {"code": "policy_denied", "message": "Not authorized"},
            }
        )
    )
    assert denied.connected_ip is None
