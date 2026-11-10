"""A restart recovers the exact upload, without replaying its probe."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent.spool import ResultSpool
from probe_core.contracts import Measurement


def test_spool_roundtrip_binding_size_and_clear(tmp_path):
    directory = tmp_path / "private"
    path = directory / "pending.json"
    spool = ResultSpool(path, "api:agent-one")
    assert spool.load() is None
    measurement = Measurement(
        job_id=uuid4(),
        attempt=1,
        kind="dns",
        vantage_id=uuid4(),
        target="https://example.com",
        configuration_hash="a" * 64,
        observed_at=datetime.now(UTC),
        probe_version="test",
        policy_version="v1",
        status="success",
    )
    payload = {"lease_token": str(uuid4()), "measurement": measurement.model_dump(mode="json")}
    spool.save(payload)
    assert ResultSpool(path, "api:agent-one").load() == payload
    with pytest.raises(ValueError):
        ResultSpool(path, "api:agent-two").load()
    assert len(list(directory.iterdir())) == 1
    spool.clear()
    assert spool.load() is None
    path.write_bytes(b"x" * 65537)
    with pytest.raises(ValueError):
        spool.load()
