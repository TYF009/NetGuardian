"""Operator-owned policy; cloud jobs cannot add local address permissions."""

import ipaddress
from dataclasses import dataclass

from probe_core.policy import CloudPolicy, PolicyDenied, public_address

PRIVATE_RANGES = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


@dataclass(frozen=True)
class LocalPolicy(CloudPolicy):
    private_cidrs: tuple[str, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        for value in self.private_cidrs:
            network = ipaddress.ip_network(value, strict=True)
            if not any(
                network.version == parent.version and network.subnet_of(parent)
                for parent in PRIVATE_RANGES
            ):
                raise ValueError("Local CIDRs must be within RFC1918 or IPv6 ULA space")

    def validate_address(self, value: str) -> str:
        try:
            return public_address(value)
        except PolicyDenied:
            address = ipaddress.ip_address(value)
            if "%" in value or getattr(address, "ipv4_mapped", None) is not None:
                raise PolicyDenied("Scoped and mapped addresses are prohibited") from None
            if any(address in ipaddress.ip_network(cidr) for cidr in self.private_cidrs):
                return str(address)
            raise
