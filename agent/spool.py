"""Single pending upload, atomically replaced; operator-owned local directory."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from probe_core.contracts import Measurement


class PendingUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lease_token: str
    measurement: Measurement


class ResultSpool:
    def __init__(self, path: Path, binding: str):
        self.path = path
        self.binding = binding
        if not path.is_absolute():
            raise ValueError("Spool path must be absolute")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("Spool paths must not be symbolic links")
        if os.name != "nt" and path.parent.stat().st_mode & 0o077:
            raise ValueError("Spool directory must be private (mode 0700)")

    def load(self):
        if not self.path.exists():
            return None
        with self.path.open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError("Spool exceeds limit")
        record = json.loads(raw)
        if record.get("binding") != self.binding:
            raise ValueError("Spool belongs to another API or agent")
        return PendingUpload.model_validate(record["upload"]).model_dump(mode="json")

    def save(self, upload):
        validated = PendingUpload.model_validate(upload).model_dump(mode="json")
        payload = json.dumps({"binding": self.binding, "upload": validated}).encode("utf-8")
        if len(payload) > 65536:
            raise RuntimeError("Pending upload exceeds spool limit")
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def clear(self):
        self.path.unlink(missing_ok=True)
