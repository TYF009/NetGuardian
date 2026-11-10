"""Verify an exported snapshot checksum offline; this does not authenticate its author."""

import argparse
import json
from pathlib import Path

from service.report_files import load_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        exported = load_export(args.report)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"checksum": "not_verified", "reason": type(exc).__name__}))
        return 1
    print(
        json.dumps(
            {
                "checksum": "verified",
                "content_hash": exported["content_hash"],
                "coverage": "snapshot only; outer export metadata is not covered",
                "authenticity": "not_verified",
                "measurement_accuracy": "not_verified",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
