"""Test-only bootstrap for the real Agent loop; never shipped as an Agent entry point."""

import asyncio
import json
import os
import socket
import ssl
import sys
from pathlib import Path

import httpx

import agent.client as client
import probe_core.executor as executor
from agent.instance import agent_instance
from agent.policy import LocalPolicy
from agent.spool import ResultSpool
from probe_core.policy import PolicyDenied


def main():
    config_path, mode = Path(sys.argv[1]), sys.argv[2]
    credential = json.loads(sys.stdin.readline())["credential"]
    print(os.getpid(), flush=True)
    context = ssl.create_default_context(
        cafile=str(Path(__file__).resolve().parents[1] / "tests/fixtures/tls/server.crt")
    )
    original_address = socket.getaddrinfo
    original_client = httpx.AsyncClient
    original_save, original_clear = ResultSpool.save, ResultSpool.clear

    def address(host, *args, **kwargs):
        if host in ("netguardian.test", b"netguardian.test"):
            host = "127.0.0.1"
        return original_address(host, *args, **kwargs)

    async def resolve(host, *, evidence=None):
        if host != "netguardian.test":
            raise PolicyDenied("Only the fixture hostname is allowed")
        return ("127.0.0.1",)

    def authorize(self, value):
        if value != "127.0.0.1":
            raise PolicyDenied("Only the loopback fixture is allowed")
        return value

    class Store:
        def get_password(self, service, account):
            return None if account.endswith(":rotation") else credential

    def checkpoint(message):
        print(message, flush=True)
        sys.stdin.read()  # Parent kills this process at the selected lifecycle boundary.
        raise RuntimeError("Fixture unexpectedly resumed")

    def save(self, upload):
        original_save(self, upload)
        if mode == "save":
            checkpoint("saved")

    def clear(self):
        original_clear(self)
        if mode == "clear":
            checkpoint("cleared")

    socket.getaddrinfo = address
    executor.resolve_public = resolve
    executor.ssl.create_default_context = lambda: context
    LocalPolicy.validate_address = authorize
    client.secure_keyring = Store
    client.httpx.AsyncClient = lambda **kwargs: original_client(verify=context, **kwargs)
    client.agent_instance = lambda identity: agent_instance(identity, config_path.parent / "locks")
    ResultSpool.save, ResultSpool.clear = save, clear
    asyncio.run(client.run(config_path, False))


if __name__ == "__main__":
    main()
