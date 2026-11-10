"""Versioned measurements shared by future cloud and agent adapters."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, model_validator

Duration = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Kind = Literal["dns", "tcp", "tls", "http", "icmp", "traceroute"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProbeRequest(Contract):
    schema_version: Literal["1"] = "1"
    job_id: UUID
    kind: Kind
    target: str = Field(min_length=1, max_length=2048)
    policy_version: str = Field(min_length=1, max_length=128)
    deadline_ms: int = Field(default=10000, ge=1, le=10000, strict=True)


def configuration_hash(request: ProbeRequest) -> str:
    """Hash the exact versioned configuration; job identity is not configuration."""
    return hashlib.sha256(request.model_dump_json(exclude={"job_id"}).encode("utf-8")).hexdigest()


class Timings(Contract):
    dns_lookup_ms: Duration | None = None
    tcp_connect_ms: Duration | None = None
    tls_handshake_ms: Duration | None = None
    http_ttfb_ms: Duration | None = None
    http_total_ms: Duration | None = None
    icmp_rtt_ms: Duration | None = None


class ProbeError(Contract):
    code: Literal[
        "policy_denied",
        "timeout",
        "resolution_failed",
        "transport_error",
        "tls_verification_failed",
        "unsupported",
        "cancelled",
    ]
    message: str = Field(min_length=1, max_length=512)
    tls_verify_code: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def validate_verification_code(self):
        if self.tls_verify_code is not None and self.code != "tls_verification_failed":
            raise ValueError("TLS verification code requires a TLS verification failure")
        return self


class RttSample(Contract):
    milliseconds: Duration
    upper_bound: bool = False


class RouteHop(Contract):
    hop: int = Field(ge=1, le=15)
    addresses: tuple[IPvAnyAddress, ...] = Field(max_length=3)
    rtt_samples: tuple[RttSample, ...] = Field(max_length=3)
    missing_replies: int = Field(ge=0, le=3)


class SystemProbeDetails(Contract):
    method: Literal["icmp_echo", "icmp_traceroute"]
    sent: int | None = Field(default=None, ge=0, le=45)
    received: int | None = Field(default=None, ge=0, le=45)
    rtt_samples: tuple[RttSample, ...] = Field(max_length=3)
    hops: tuple[RouteHop, ...] = Field(max_length=15)
    destination_reached: bool


class DnsAnswer(Contract):
    record_type: Literal["A", "AAAA"]
    addresses: tuple[IPvAnyAddress, ...] = Field(max_length=16)
    ttl_seconds: int = Field(ge=0, le=4294967295)
    canonical_name: str = Field(max_length=255)
    resolver: str | None = Field(default=None, max_length=255)
    resolver_port: int | None = Field(default=None, ge=1, le=65535)


class DnsDetails(Contract):
    used_dns: bool
    answers: tuple[DnsAnswer, ...] = Field(max_length=2)


class TlsDetails(Contract):
    protocol: str = Field(min_length=1, max_length=32)
    cipher: str = Field(min_length=1, max_length=128)
    cipher_bits: int = Field(ge=0, le=65536, strict=True)
    leaf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    not_before: AwareDatetime
    not_after: AwareDatetime
    hostname_verified: Literal[True] = True


class Measurement(Contract):
    schema_version: Literal["1"] = "1"
    job_id: UUID
    attempt: int = Field(ge=1, strict=True)
    kind: Kind
    vantage_id: UUID
    target: str = Field(min_length=1, max_length=2048)
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    resolved_ips: tuple[IPvAnyAddress, ...] = ()
    connected_ip: IPvAnyAddress | None = None
    observed_at: AwareDatetime
    received_at: AwareDatetime | None = None
    probe_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    status: Literal["success", "error", "timeout", "denied", "unsupported", "cancelled"]
    timings: Timings = Field(default_factory=Timings)
    error: ProbeError | None = None
    system_probe: SystemProbeDetails | None = None
    dns: DnsDetails | None = None
    tls: TlsDetails | None = None
    http_status: int | None = Field(default=None, ge=100, le=599, strict=True)

    @model_validator(mode="after")
    def validate_outcome(self):
        if (self.status == "success") != (self.error is None):
            raise ValueError("Success requires no error; other outcomes require an error")
        if self.error is not None and self.error.code == "tls_verification_failed":
            if self.kind not in {"tls", "http"} or self.status != "error" or self.tls is not None:
                raise ValueError("TLS verification failure cannot carry verified TLS evidence")
        if self.tls is not None and self.kind not in {"tls", "http"}:
            raise ValueError("TLS details require a TLS or HTTP probe")
        if self.http_status is not None and self.kind != "http":
            raise ValueError("HTTP status belongs only to HTTP measurements")
        if self.kind != "icmp" and self.timings.icmp_rtt_ms is not None:
            raise ValueError("ICMP RTT cannot describe another probe kind")
        if self.kind != "http" and (
            self.timings.http_ttfb_ms is not None or self.timings.http_total_ms is not None
        ):
            raise ValueError("HTTP timings cannot describe another probe kind")
        if self.connected_ip is not None and self.connected_ip not in self.resolved_ips:
            raise ValueError("Connected address must be recorded in resolved addresses")
        expected_errors = {
            "denied": "policy_denied",
            "timeout": "timeout",
            "unsupported": "unsupported",
            "cancelled": "cancelled",
        }
        if self.status in expected_errors and self.error.code != expected_errors[self.status]:
            raise ValueError("Error code does not match outcome")
        return self
