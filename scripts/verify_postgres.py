"""Run isolated PostgreSQL integration and dump/restore verification.

Uses installed binaries; never downloads software, registers a service, or connects
to an existing cluster. Temporary artifacts remain for inspection after shutdown.
"""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg import sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=Path, required=True, help="PostgreSQL bin directory")
    args = parser.parse_args()
    bin_dir = args.bin_dir.resolve(strict=True)
    suffix = ".exe" if os.name == "nt" else ""
    for tool in ("postgres", "initdb", "pg_ctl", "pg_dump", "pg_restore"):
        if not (bin_dir / (tool + suffix)).is_file():
            parser.error(f"Missing PostgreSQL tool: {tool}")
    if os.name == "nt" and not str(bin_dir).isascii():
        parser.error("Use an ASCII binary path on Windows (initdb restricted-token limitation)")
    repository = Path(__file__).resolve().parents[1]
    run_dir = Path(tempfile.mkdtemp(prefix="NetGuardian-pg-validation-"))
    if os.name == "nt" and not str(run_dir).isascii():
        parser.error("Use an ASCII system temporary directory on Windows")
    data = run_dir / "data"
    password = secrets.token_urlsafe(32)
    password_file = run_dir / "init-password.txt"
    password_file.write_text(password, encoding="ascii")
    # Avoid inherited libpq options or application URLs redirecting this isolated run.
    for key in list(os.environ):
        if key.startswith("PG") or key == "NETGUARDIAN_DATABASE_URL":
            os.environ.pop(key)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["PGPASSWORD"] = password
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    def run(name, *args):
        output = run_dir / (name + "-output.log")
        with output.open("wb") as stream:
            result = subprocess.run(  # noqa: S603 - fixed tools from operator-selected PostgreSQL directory
                [str(bin_dir / (name + (".exe" if os.name == "nt" else ""))), *map(str, args)],
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        text = output.read_text(encoding="utf-8", errors="replace")
        if result.returncode:
            print(text, flush=True)
            raise RuntimeError(name + " failed")
        return text.strip()

    started = False
    try:
        print(run("postgres", "--version"), flush=True)
        print("Initializing disposable SCRAM-authenticated cluster", flush=True)
        run(
            "initdb",
            "-D",
            data,
            "-U",
            "netguardian",
            "--auth=scram-sha-256",
            "--encoding=UTF8",
            "--locale=C",
            "--pwfile",
            password_file,
        )
        password_file.unlink()
        print("Cluster initialized; starting server", flush=True)
        run(
            "pg_ctl",
            "-D",
            data,
            "-l",
            run_dir / "postgres.log",
            "-o",
            f"-h 127.0.0.1 -p {port}",
            "-w",
            "start",
        )
        started = True
        print("Server started; connecting", flush=True)
        connect = dict(
            host="127.0.0.1", port=port, user="netguardian", password=password, connect_timeout=5
        )
        with psycopg.connect(dbname="postgres", autocommit=True, **connect) as connection:
            connection.execute("CREATE DATABASE netguardian_test")
            connection.execute("CREATE DATABASE netguardian_restore_test")
        env["NETGUARDIAN_TEST_POSTGRES_URL"] = (
            f"postgresql+psycopg://netguardian:{password}@127.0.0.1:{port}/netguardian_test"
        )
        print("Starting integration tests", flush=True)
        completed = subprocess.run(  # noqa: S603 - fixed repository test command
            [
                sys.executable,
                "-m",
                "pytest",
                "integration/test_postgres.py",
                "integration/test_agent_workflow.py",
                "-q",
                "--tb=short",
            ],
            env=env,
            cwd=repository,
            timeout=180,
        )
        if completed.returncode:
            raise RuntimeError("PostgreSQL integration tests failed")
        archive = run_dir / "backup.dump"
        run(
            "pg_dump",
            "-h",
            "127.0.0.1",
            "-p",
            port,
            "-U",
            "netguardian",
            "-d",
            "netguardian_test",
            "-Fc",
            "-f",
            archive,
        )
        run(
            "pg_restore",
            "-h",
            "127.0.0.1",
            "-p",
            port,
            "-U",
            "netguardian",
            "-d",
            "netguardian_restore_test",
            "--exit-on-error",
            archive,
        )

        def snapshot(database):
            with psycopg.connect(dbname=database, **connect) as connection:
                tables = [
                    r[0]
                    for r in connection.execute(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname='public' ORDER BY tablename"
                    )
                ]
                result = {}
                for table in tables:
                    rows = connection.execute(
                        sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
                    ).fetchall()
                    serialized = sorted(
                        json.dumps(row, sort_keys=True, default=str) for row in rows
                    )
                    result[table] = {
                        "rows": len(rows),
                        "digest": hashlib.sha256(json.dumps(serialized).encode()).hexdigest(),
                    }
                return result

        original, restored = snapshot("netguardian_test"), snapshot("netguardian_restore_test")
        if original != restored:
            raise RuntimeError("Restore differs from source")
        if original["jobs"]["rows"] == 0 or original["reports"]["rows"] == 0:
            raise RuntimeError("Expected populated evidence fixture")
        (run_dir / "validation.json").write_text(json.dumps(original, indent=2), encoding="utf-8")
        print(
            "Backup/restore row counts and content digests match for",
            len(original),
            "tables",
            flush=True,
        )
        print(json.dumps({name: value["rows"] for name, value in original.items()}), flush=True)
    finally:
        password_file.unlink(missing_ok=True)
        if started or (data / "postmaster.pid").exists():
            run("pg_ctl", "-D", data, "-m", "fast", "-w", "stop")
            print("Disposable PostgreSQL stopped; no system service installed", flush=True)

    print("Verification artifacts:", run_dir, flush=True)


if __name__ == "__main__":
    main()
