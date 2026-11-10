"""Bounded offline loading of exported snapshots; no network or database access."""

import json
import secrets
from pathlib import Path

from service.evidence import snapshot_hash


def load_export(path: Path):
    with path.open("rb") as source:
        raw = source.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Report export exceeds the 4 MiB verification limit")
    exported = json.loads(raw)
    if not isinstance(exported, dict) or not isinstance(exported.get("snapshot"), dict):
        raise ValueError("Report export must contain a snapshot object")
    snapshot = exported["snapshot"]
    expected = exported.get("content_hash")
    if (
        not isinstance(expected, str)
        or not expected.isascii()
        or not secrets.compare_digest(snapshot_hash(snapshot), expected)
    ):
        raise ValueError("Report checksum does not match")
    return exported
