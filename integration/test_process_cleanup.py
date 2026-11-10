"""Real local subprocess cleanup; fixed Python fixtures, no shell or network."""

import asyncio
import sys

import pytest

from probe_core.system_tools import run_bounded


@pytest.mark.parametrize("failure", ["cancel", "timeout", "output"])
def test_bounded_runner_reaps_child(monkeypatch, failure):
    async def scenario():
        children = []
        started = asyncio.Event()
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            children.append(process)
            started.set()
            return process

        source = (
            "import sys; sys.stdout.write('x' * 70000); sys.stdout.flush(); "
            "import time; time.sleep(60)"
            if failure == "output"
            else "import time; time.sleep(60)"
        )
        with monkeypatch.context() as patch:
            patch.setattr("probe_core.system_tools.asyncio.create_subprocess_exec", capture)
            task = asyncio.create_task(run_bounded([sys.executable, "-c", source]))
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                if failure == "cancel":
                    task.cancel()
                    expected = asyncio.CancelledError
                else:
                    expected = TimeoutError if failure == "timeout" else ValueError
                with pytest.raises(expected):
                    await asyncio.wait_for(task, timeout=15)
                assert len(children) == 1
                assert children[0].returncode is not None
            finally:
                # Test failure cleanup never leaves the deliberately sleeping fixture alive.
                for process in children:
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
