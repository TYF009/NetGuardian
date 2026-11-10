"""Pure cloud policy decisions. Plans are not permission to bypass transport checks."""

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


class PolicyDenied(ValueError):
    """The target must not be resolved or contacted."""


def canonical_host(value: str) -> str:
    if not value or len(value) > 253 or not value.isascii():
        raise PolicyDenied("An ASCII hostname or canonical IP is required")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        host = value.lower()
        if not re.fullmatch(r"[a-z0-9.-]+", host) or host.endswith("."):
            raise PolicyDenied("Invalid hostname") from None
        labels = host.split(".")
        if len(labels) < 2 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
        ):
            raise PolicyDenied("Invalid hostname labels") from None
        if not re.fullmatch(r"[a-z]{2,63}", labels[-1]):
            raise PolicyDenied("Ambiguous numeric hostname") from None
        return host
    if "%" in value:
        raise PolicyDenied("Scoped IP addresses are prohibited")
    return str(address)


def public_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise PolicyDenied("Invalid DNS answer") from exc
    # Conservative exclusions supplement Python 3.11's address registry.
    excluded = (
        "192.0.0.0/24",
        "192.88.99.0/24",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "2001::/23",
        "2002::/16",
        "3fff::/20",
    )
    if (
        "%" in value
        or not address.is_global
        or address.is_multicast
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or getattr(address, "ipv4_mapped", None) is not None
        or any(address in ipaddress.ip_network(net) for net in excluded)
    ):
        raise PolicyDenied("Destination is not an approved public unicast address")
    return str(address)


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    scheme: str
    path: str


def parse_target(url: str) -> Target:
    if len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in url) or "\\" in url:
        raise PolicyDenied("Invalid URL characters")
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise PolicyDenied("Only HTTP(S) targets are supported by this policy")
        if parts.username is not None or parts.password is not None or parts.fragment:
            raise PolicyDenied("Credentials and fragments are prohibited")
        host = canonical_host(parts.hostname)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if parts.netloc.endswith(":") or parts.port == 0:
            raise PolicyDenied("Invalid port")
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        return Target(host, port, parts.scheme, path)
    except ValueError as exc:
        raise PolicyDenied("Invalid target URL") from exc


@dataclass(frozen=True)
class CloudPolicy:
    """Construct only from trusted administrator configuration, never request data."""

    version: str
    allowed_origins: frozenset[tuple[str, int, str]] = frozenset()
    revoked: bool = False
    max_redirects: int = 3

    def __post_init__(self):
        if (
            not self.version
            or type(self.max_redirects) is not int
            or not 0 <= self.max_redirects <= 3
        ):
            raise ValueError("Invalid policy configuration")
        if not isinstance(self.allowed_origins, frozenset):
            raise ValueError("Origins must be immutable")
        for host, port, scheme in self.allowed_origins:
            if canonical_host(host) != host or type(port) is not int or not 1 <= port <= 65535:
                raise ValueError("Invalid origin")
            if scheme not in {"http", "https"}:
                raise ValueError("Unsupported scheme")

    def validate_address(self, value: str) -> str:
        return public_address(value)

    def authorize(self, url: str) -> Target:
        target = parse_target(url)
        if self.revoked or (target.host, target.port, target.scheme) not in self.allowed_origins:
            raise PolicyDenied("Origin not authorized")
        return target


@dataclass(frozen=True)
class ConnectionPlan:
    target: Target
    addresses: tuple[str, ...]
    policy_version: str


def plan_connection(policy: CloudPolicy, url: str, answers: tuple[str, ...]) -> ConnectionPlan:
    target = policy.authorize(url)
    if not answers or len(answers) > 16:
        raise PolicyDenied("DNS answer count outside limits")
    addresses = tuple(dict.fromkeys(policy.validate_address(answer) for answer in answers))
    try:
        literal = str(ipaddress.ip_address(target.host))
    except ValueError:
        literal = None
    if literal is not None and addresses != (literal,):
        raise PolicyDenied("Literal destination mismatch")
    return ConnectionPlan(target, addresses, policy.version)


def redirect_target(policy: CloudPolicy, current: str, location: str, hops: int) -> str:
    if type(hops) is not int or not 0 <= hops < policy.max_redirects:
        raise PolicyDenied("Redirect budget exhausted")
    policy.authorize(current)
    if not location or any(ord(c) <= 32 or ord(c) >= 127 for c in location) or "\\" in location:
        raise PolicyDenied("Invalid redirect")
    destination = urljoin(current, location)
    target = policy.authorize(destination)
    if parse_target(current).scheme == "https" and target.scheme != "https":
        raise PolicyDenied("TLS downgrade prohibited")
    return destination
