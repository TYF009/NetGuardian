"""Build a source archive from an explicit allowlist, excluding credentials/tests."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names = [
        line.strip()
        for line in (root / "packaging/source-files.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate source paths")
    payloads = {}
    for name in sorted(names):
        relative = Path(name)
        forbidden = {
            "tests",
            "integration",
            ".git",
            ".venv",
            "node_modules",
            ".next",
            ".pytest_cache",
            ".netguardian-local",
        }
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or any(part in forbidden for part in relative.parts)
            or relative.suffix.lower() in {".key", ".pem", ".pfx", ".p12", ".db", ".log"}
            or relative.name in {".env", "secrets.toml", "config.local.json"}
        ):
            raise ValueError(f"Not an allowed release path: {name}")
        path = root / relative
        if path.is_symlink() or any(
            parent.is_symlink() for parent in path.parents if parent != root
        ):
            raise ValueError(f"Symbolic link is not a release source: {name}")
        if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
            raise ValueError(f"Invalid source file: {name}")
        data = path.read_bytes()
        if b"PRIVATE " + b"KEY-----" in data:
            raise ValueError(f"Private key material is not allowed: {name}")
        payloads[name] = data
    manifest = {
        "format_version": 1,
        "kind": "unsigned-source-snapshot",
        "platform_scope": "Windows local; Linux runtime deferred",
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in payloads.items()
        },
        "limitations": [
            "Dependencies, build outputs and test suites are not bundled.",
            "Full verification requires the original source checkout.",
            "Hashes detect changes; they do not authenticate a publisher.",
        ],
    }
    payloads["BUNDLE_MANIFEST.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as destination, ZipFile(destination, "w") as archive:
        for name, data in sorted(payloads.items()):
            info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    with args.output.with_suffix(args.output.suffix + ".sha256").open(
        "x", encoding="utf-8"
    ) as output:
        output.write(f"{checksum}  {args.output.name}\n")
    print(f"Created {len(payloads) - 1} source files; SHA-256 {checksum}")


if __name__ == "__main__":
    main()
