"""Block probe I/O in every test; allow only the Windows asyncio self-pipe."""

import inspect
import socket
import subprocess

import pytest


@pytest.fixture(autouse=True)
def forbid_network_and_commands(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected network or process execution")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        # Windows asyncio creates an internal socketpair for event-loop wakeups.
        caller = inspect.currentframe().f_back
        if caller.f_code.co_name == "socketpair" and caller.f_code.co_filename == socket.__file__:
            return original_connect(sock, address)
        return forbidden(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
