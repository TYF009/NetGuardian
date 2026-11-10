"""Environment-only administrator configuration; no client-created policies."""

import hashlib
import json
import os
from dataclasses import dataclass

from probe_core.policy import CloudPolicy, parse_target


@dataclass(frozen=True)
class Settings:
    database_url: str
    credentials: dict[str, str]
    policies: dict[str, CloudPolicy]

    @classmethod
    def from_environment(cls):
        credentials = json.loads(os.environ.get("NETGUARDIAN_TOKENS", "{}"))
        if (
            not isinstance(credentials, dict)
            or not credentials
            or any(
                not isinstance(token, str)
                or not token.isascii()
                or not 32 <= len(token) <= 512
                or not isinstance(tenant, str)
                or not 1 <= len(tenant) <= 128
                for token, tenant in credentials.items()
            )
        ):
            raise ValueError(
                "Configure NETGUARDIAN_TOKENS with random tokens of at least 32 characters"
            )
        policies = {}
        configured_origins = json.loads(os.environ.get("NETGUARDIAN_ORIGINS", "{}"))
        if not isinstance(configured_origins, dict):
            raise ValueError("Origin policies must be a workspace mapping")
        for workspace, urls in configured_origins.items():
            if (
                workspace not in credentials.values()
                or not isinstance(urls, list)
                or len(urls) > 100
            ):
                raise ValueError("Invalid workspace origin policy")
            origins = [parse_target(url) for url in urls]
            policies[workspace] = CloudPolicy(
                hashlib.sha256(json.dumps(sorted(urls)).encode()).hexdigest(),
                frozenset((t.host, t.port, t.scheme) for t in origins),
            )
        return cls(
            os.environ.get("NETGUARDIAN_DATABASE_URL", "sqlite:///netguardian.db"),
            credentials,
            policies,
        )
