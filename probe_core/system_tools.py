"""Fixed platform commands with numeric destinations and bounded subprocess output."""

import asyncio
import ipaddress
import locale
import os
import re
import sys
from contextlib import suppress
from pathlib import Path


def command_for(kind: str, address: str, platform: str):
    address = str(ipaddress.ip_address(address))
    family = "6" if ":" in address else "4"
    if platform == "win32":
        root = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
        if kind == "icmp":
            return [str(root / "PING.EXE"), f"-{family}", "-n", "1", "-w", "1000", address]
        if kind == "traceroute":
            return [str(root / "TRACERT.EXE"), f"-{family}", "-d", "-h", "15", "-w", "200", address]
    if platform.startswith("linux"):
        name = "ping" if kind == "icmp" else "traceroute"
        executable = next(
            (
                str(p / name)
                for p in (Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"))
                if (p / name).is_file()
            ),
            f"/usr/bin/{name}",
        )
        if kind == "icmp":
            return [executable, f"-{family}", "-n", "-c", "1", "-W", "1", address]
        if kind == "traceroute":
            return [
                executable,
                f"-{family}",
                "-I",
                "-n",
                "-m",
                "15",
                "-q",
                "1",
                "-w",
                "0.2",
                address,
            ]
    raise NotImplementedError("Platform probe is unavailable")


async def run_bounded(arguments):
    if not Path(arguments[0]).is_file():
        raise NotImplementedError("Required system probe tool is not installed")
    environment = dict(os.environ, LC_ALL="C", LANG="C")
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=environment,
        **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),
    )
    output = bytearray()
    try:
        async with asyncio.timeout(9):
            while chunk := await process.stdout.read(4096):
                output.extend(chunk)
                if len(output) > 65536:
                    raise ValueError("System probe output exceeds limit")
            code = await process.wait()
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await process.wait()
    return code, output.decode(locale.getpreferredencoding(False), errors="replace")


def parse_output(kind: str, text: str, address: str):
    samples = []
    for match in re.finditer(r"(?:time|时间)\s*([=<])\s*(\d+(?:\.\d+)?)\s*ms", text, re.I):
        samples.append({"milliseconds": float(match[2]), "upper_bound": match[1] == "<"})
    if kind == "icmp":
        return {
            "method": "icmp_echo",
            "sent": 1,
            "received": min(1, len(samples)),
            "rtt_samples": samples[:1],
            "hops": [],
            "destination_reached": bool(samples),
        }
    hops = []
    for line in text.splitlines():
        match = re.match(r"^\s*(\d+)\s+(.+)$", line)
        if not match or not 1 <= int(match[1]) <= 15:
            continue
        addresses = []
        for token in match[2].split():
            try:
                addresses.append(str(ipaddress.ip_address(token.strip("[]()"))))
            except ValueError:
                pass
        rtts = [
            {"milliseconds": float(m[2]), "upper_bound": m[1] == "<"}
            for m in re.finditer(r"(<)?\s*(\d+(?:\.\d+)?)\s*ms", match[2], re.I)
        ]
        hops.append(
            {
                "hop": int(match[1]),
                "addresses": addresses[:3],
                "rtt_samples": rtts[:3],
                "missing_replies": match[2].count("*"),
            }
        )
    return {
        "method": "icmp_traceroute",
        "sent": None,
        "received": None,
        "rtt_samples": [],
        "hops": hops[:15],
        "destination_reached": any(address in h["addresses"] for h in hops),
    }


async def system_probe(kind, address):
    arguments = command_for(kind, address, sys.platform)
    _code, text = await run_bounded(arguments)
    if re.search(
        r"operation not permitted|permission denied|access is denied|requires.*privilege",
        text,
        re.I,
    ):
        raise PermissionError("System probe permission unavailable")
    result = parse_output(kind, text, address)
    if not result["hops"] and not result["rtt_samples"]:
        raise OSError("System probe failed or received no reply")
    return result
