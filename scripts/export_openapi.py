"""Export deterministic OpenAPI without reading operator credentials or databases."""

import argparse
import json
import tempfile
from pathlib import Path

from service.api import create_app
from service.schema import upgrade
from service.settings import Settings


def generate():
    # This temporary schema database has no operator data and never starts a server.
    with tempfile.TemporaryDirectory(prefix="netguardian-schema-") as directory:
        url = "sqlite:///" + (Path(directory) / "schema.db").as_posix()
        upgrade(url)
        app = create_app(Settings(url, {"schema-generation-only-token-00000": "schema"}, {}))
        try:
            return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
        finally:
            with app.state.sessions() as session:
                session.get_bind().dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "web" / "openapi.json"
    generated = generate()
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != generated:
            raise SystemExit("OpenAPI is stale: run python -m scripts.export_openapi")
        print("OpenAPI matches the current server")
    else:
        destination.write_text(generated, encoding="utf-8")
        print("Exported web/openapi.json")


if __name__ == "__main__":
    main()
