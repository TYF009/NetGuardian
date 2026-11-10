"""Portable agent. Requires verified HTTPS and an OS-backed credential store."""

import argparse
import asyncio
import getpass
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import keyring
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from agent.instance import agent_instance
from agent.policy import LocalPolicy
from agent.spool import ResultSpool
from probe_core.contracts import ProbeRequest
from probe_core.executor import execute_probe
from probe_core.policy import parse_target


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_url: str
    agent_id: UUID | None = None
    origins: list[str] = Field(default_factory=list, max_length=20)
    private_cidrs: tuple[str, ...] = ()
    spool_path: Path | None = None

    def validate_server(self):
        parsed = urlsplit(self.api_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Agent control URL must be an HTTPS origin without credentials")

    def policy(self, version: str):
        targets = [parse_target(url) for url in self.origins]
        return LocalPolicy(
            version,
            frozenset((t.host, t.port, t.scheme) for t in targets),
            private_cidrs=self.private_cidrs,
        )


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: UUID
    credential: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class UploadAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: Literal[True]
    duplicate: bool = Field(strict=True)


class Assignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: ProbeRequest | None
    lease_token: str | None = None
    attempt: int = Field(default=1, ge=1, le=3)
    expires_at: AwareDatetime | None = None


async def process_assignment(config: AgentConfig, data: dict, execute=execute_probe):
    assignment = Assignment.model_validate(data)
    if assignment.job is None:
        return None
    if (
        assignment.expires_at is None
        or assignment.expires_at <= datetime.now(UTC)
        or assignment.lease_token is None
        or config.agent_id is None
    ):
        raise ValueError("Expired or incomplete assignment")
    request = assignment.job
    result = await execute(request, config.policy(request.policy_version), config.agent_id)
    result = result.model_copy(update={"attempt": assignment.attempt})
    return {"lease_token": assignment.lease_token, "measurement": result.model_dump(mode="json")}


def secure_keyring():
    backend = keyring.get_keyring()
    module = type(backend).__module__
    if not module.startswith(
        ("keyring.backends.Windows", "keyring.backends.SecretService", "keyring.backends.kwallet")
    ):
        raise RuntimeError("Configure Windows Credential Manager or Linux Secret Service/KWallet")
    return backend


async def control_request(client, path, payload=None):
    """Bound response bytes and total duration, including slow streaming peers."""
    async with asyncio.timeout(20):
        async with client.stream(
            "POST", path, json=payload, headers={"Accept-Encoding": "identity"}
        ) as response:
            response.raise_for_status()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Compressed control responses are not supported")
            content = bytearray()
            async for chunk in response.aiter_raw():
                if len(content) + len(chunk) > 65536:
                    raise ValueError("Control response exceeds limit")
                content.extend(chunk)
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Control response must be an object")
            return data


async def rotate_credential(client, store, service, account, current, initiate=False):
    pending_account = account + ":rotation"
    pending = store.get_password(service, pending_account)
    if not pending and not initiate:
        return current
    if not pending:
        pending = secrets.token_urlsafe(32)
        store.set_password(service, pending_account, pending)
    # A lost response may mean the server already replaced the old credential.
    client.headers["Authorization"] = f"Bearer {current}"
    try:
        result = await control_request(client, "/api/agent/rotate", {"credential": pending})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        client.headers["Authorization"] = f"Bearer {pending}"
        result = await control_request(client, "/api/agent/rotate", {"credential": pending})
    if result != {"rotated": True}:
        raise ValueError("Invalid rotation acknowledgement")
    store.set_password(service, account, pending)
    store.delete_password(service, pending_account)
    client.headers["Authorization"] = f"Bearer {pending}"
    return pending


async def run(config_path: Path, enroll: bool, rotate=False):
    config = AgentConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    config.validate_server()
    server = urlsplit(config.api_url)
    identity = f"{server.hostname}:{server.port or 443}:{config.agent_id or config_path.resolve()}"
    with agent_instance(identity):
        await run_locked(config_path, config, enroll, rotate)


async def run_locked(config_path, config, enroll, rotate):
    store = secure_keyring()
    service = f"NetGuardian:{config.api_url.rstrip('/')}"
    async with httpx.AsyncClient(
        base_url=config.api_url.rstrip("/"), timeout=15, follow_redirects=False, trust_env=False
    ) as client:
        if enroll:
            enrolled = await control_request(
                client,
                "/api/agent/enroll",
                {"token": getpass.getpass("One-time enrollment token: ")},
            )
            enrolled = EnrollmentResponse.model_validate(enrolled)
            agent_id = str(enrolled.agent_id)
            store.set_password(service, agent_id, enrolled.credential)
            config = config.model_copy(update={"agent_id": UUID(agent_id)})
            config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
            print("Enrollment complete; credential stored in the OS keyring.")
            return
        if config.agent_id is None:
            raise ValueError("Enroll this agent first")
        credential = store.get_password(service, str(config.agent_id))
        if not credential:
            raise ValueError("No stored agent credential")
        credential = await rotate_credential(
            client, store, service, str(config.agent_id), credential, initiate=rotate
        )
        client.headers["Authorization"] = f"Bearer {credential}"
        if rotate:
            print("Credential rotation complete.")
            return
        spool = (
            ResultSpool(config.spool_path, f"{service}:{config.agent_id}")
            if config.spool_path
            else None
        )
        pending = spool.load() if spool else None
        failures = 0
        while True:
            try:
                if pending is None:
                    data = await control_request(client, "/api/agent/poll")
                    pending = await process_assignment(config, data)
                    if pending is not None and spool:
                        spool.save(pending)
                if pending is not None:
                    try:
                        acknowledgement = await control_request(
                            client, "/api/agent/results", pending
                        )
                        UploadAcknowledgement.model_validate(acknowledgement)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code not in (404, 409, 422):
                            raise
                    if spool:
                        spool.clear()
                    pending = None  # Terminal lease rejection must not re-execute a job.
                failures = 0
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (401, 403):
                    raise RuntimeError("Agent access revoked or unauthorized") from None
                failures += 1
                logging.warning("Control API rejected request; retrying with backoff")
            except (httpx.HTTPError, ValueError, TimeoutError):
                failures += 1
                logging.warning("Control API unavailable or invalid assignment; retrying")
            await asyncio.sleep(min(60, 2 ** min(failures, 5)) + secrets.randbelow(1000) / 1000 + 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetGuardian outbound HTTPS agent")
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--enroll", action="store_true")
    mode.add_argument("--rotate-credential", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.config, args.enroll, args.rotate_credential))
