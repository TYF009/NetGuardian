"""A killed launcher cannot leave its child or grandchild running on Windows."""

import asyncio
import ctypes
import json
import os
import signal
import sys
from ctypes import wintypes
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object lifecycle")
def test_job_reaps_descendants_after_owner_termination():
    async def scenario():
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        grandchild = "import os,time; print(os.getpid(),flush=True); time.sleep(60)"
        child = (
            "import os,subprocess,sys,time,json; "
            f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}],stdout=subprocess.PIPE); "
            "print(json.dumps([os.getpid(),int(p.stdout.readline())]),flush=True); time.sleep(60)"
        )
        owner = (
            "import os,subprocess,sys,json; "
            "from scripts.windows_job import contain_launcher; contain_launcher(); "
            f"p=subprocess.Popen([sys.executable,'-c',{child!r}],stdout=subprocess.PIPE); "
            "print(json.dumps([os.getpid(),*json.loads(p.stdout.readline())]),flush=True); "
            "sys.stdin.read()"
        )
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            owner,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(__file__).resolve().parents[1],
        )
        owner_pid = None
        handles = []
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=10)
            owner_pid, *descendants = json.loads(line)
            for pid in descendants:
                handle = kernel.OpenProcess(0x100001, False, pid)  # SYNCHRONIZE | TERMINATE
                assert handle
                handles.append(handle)
                assert kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT: alive
            os.kill(owner_pid, signal.SIGTERM)
            owner_pid = None
            await asyncio.wait_for(process.wait(), timeout=10)
            for handle in handles:
                assert kernel.WaitForSingleObject(handle, 5000) == 0  # Exited, not PID reuse.
        finally:
            if owner_pid is not None:
                try:
                    os.kill(owner_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            elif process.returncode is None:
                process.kill()
            for handle in handles:
                if kernel.WaitForSingleObject(handle, 0) == 258:
                    kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
            process.stdin.close()
            await asyncio.wait_for(process.wait(), timeout=10)

    asyncio.run(scenario())
