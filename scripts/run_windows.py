"""Supervise a loopback-only Windows API, worker and production Web build."""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from scripts.windows_job import contain_launcher
from service.database import database
from service.schema import require_schema, upgrade
from service.settings import Settings
from service.worker import configured_vantage


def free_port(port):
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", port))


def main():
    # Redirected Windows consoles may use an encoding without the checkout characters.
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true", help="Explicitly upgrade the database")
    parser.add_argument("--check", action="store_true", help="Check prerequisites without starting")
    parser.add_argument(
        "--run-seconds", type=int, default=0, help="Stop after this many ready seconds"
    )
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This launcher is supported on Windows only")
    if args.run_seconds < 0:
        parser.error("--run-seconds must be nonnegative")
    if args.check and args.migrate:
        parser.error("--check cannot be combined with --migrate")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    settings = Settings.from_environment()
    configured_vantage()
    node = shutil.which("node")
    next_cli = root / "web/node_modules/next/dist/bin/next"
    if not node or not next_cli.is_file() or not (root / "web/.next/BUILD_ID").is_file():
        parser.error("Install Web dependencies and run pnpm build in web/ first")
    taskkill = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
    if not taskkill.is_file():
        parser.error("Windows process-tree cleanup tool is unavailable")
    for port in (8000, 3000):
        free_port(port)
    if args.migrate:
        upgrade(settings.database_url)
    engine, _ = database(settings.database_url)
    try:
        require_schema(engine)
    finally:
        engine.dispose()
    if args.check:
        print("Configuration, database schema, Web build and loopback ports are ready.")
        return
    contain_launcher()
    # Do not persist credentials, print them, or pass them in command-line arguments.
    env = dict(os.environ)
    env["NETGUARDIAN_API_URL"] = "http://127.0.0.1:8000"
    env["PYTHONUNBUFFERED"] = "1"
    log_root = root / ".netguardian-local"
    log_root.mkdir(exist_ok=True)
    log_dir = Path(tempfile.mkdtemp(prefix="run-", dir=log_root))
    children = []
    logs = []

    def start(name, command, cwd):
        log = (log_dir / f"{name}.log").open("wb")
        logs.append(log)
        child_env = env
        if name == "web":
            child_env = {
                key: value for key, value in env.items() if not key.startswith("NETGUARDIAN_")
            }
            child_env["NETGUARDIAN_API_URL"] = "http://127.0.0.1:8000"
        process = subprocess.Popen(  # noqa: S603 - fixed local entry points, no shell
            command,
            cwd=cwd,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        children.append((name, process))

    def check_children():
        for name, process in children:
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited; inspect {log_dir / (name + '.log')}")

    def wait_ready(url):
        deadline = time.monotonic() + 45
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=1) as client:
            while time.monotonic() < deadline:
                check_children()
                try:
                    if client.get(url).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise RuntimeError(f"Startup timed out; inspect logs in {log_dir}")

    try:
        start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "service.api:app_factory",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ],
            root,
        )
        wait_ready("http://127.0.0.1:8000/ready")
        start("worker", [sys.executable, "-m", "service.worker"], root)
        start(
            "web",
            [node, str(next_cli), "start", "--hostname", "127.0.0.1", "--port", "3000"],
            root / "web",
        )
        wait_ready("http://127.0.0.1:3000")
        print(f"NetGuardian ready at http://127.0.0.1:3000; logs: {log_dir}", flush=True)
        print("Use your configured workspace token. Press Ctrl+C to stop.", flush=True)
        deadline = time.monotonic() + args.run_seconds if args.run_seconds else None
        while deadline is None or time.monotonic() < deadline:
            check_children()
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("Stopping local services.")
    finally:
        # Only kill process trees created here, and only while their handles are live.
        # Interrupted measurements recover through the existing lease expiry rules.
        for _name, process in reversed(children):
            if process.poll() is None:
                subprocess.run(  # noqa: S603 - fixed Windows cleanup tool and owned PID
                    [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15,
                )
                process.wait(timeout=15)
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
