"""A real second process cannot share an Agent lock; killed owners release it."""

import asyncio
import os
import signal
import sys
from pathlib import Path

import pytest

from agent.instance import agent_instance


def test_process_exclusion_and_crash_release(tmp_path):
    async def scenario():
        source = (
            "import sys, os; from pathlib import Path; from agent.instance import agent_instance; "
            "guard=agent_instance('fixture',Path(sys.argv[1])); guard.__enter__(); "
            "print(f'locked:{os.getpid()}',flush=True); sys.stdin.read()"
        )
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            source,
            str(tmp_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(__file__).resolve().parents[1],
        )
        owner_pid = None
        try:
            ready = (await asyncio.wait_for(child.stdout.readline(), timeout=5)).strip()
            assert ready.startswith(b"locked:")
            owner_pid = int(ready.split(b":")[1])
            with (
                pytest.raises(RuntimeError, match="agent lock"),
                agent_instance("fixture", tmp_path),
            ):
                pytest.fail("Another process acquired the same identity")
        finally:
            if owner_pid is not None:
                # Windows venv launchers may have a distinct PID from the lock owner.
                try:
                    os.kill(owner_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif child.returncode is None:
                child.kill()
            child.stdin.close()
            await asyncio.wait_for(child.wait(), timeout=5)
        with agent_instance("fixture", tmp_path):
            pass
        with agent_instance("other-agent", tmp_path), agent_instance("fixture", tmp_path):
            pass

    asyncio.run(scenario())
