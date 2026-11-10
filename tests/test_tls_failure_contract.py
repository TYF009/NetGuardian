"""TLS failures cannot be mislabeled as a verified successful handshake."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from probe_core.contracts import Measurement, ProbeError


def test_verification_failure_semantics():
    with pytest.raises(ValidationError):
        ProbeError(code="transport_error", message="Fixture", tls_verify_code=20)
    fields = dict(
        job_id=uuid4(),
        attempt=1,
        kind="tls",
        target="https://example.com",
        vantage_id=uuid4(),
        configuration_hash="a" * 64,
        observed_at=datetime.now(UTC),
        probe_version="fixture",
        policy_version="fixture",
        status="error",
        error=ProbeError(code="tls_verification_failed", message="Fixture", tls_verify_code=20),
    )
    assert Measurement(**fields).error.tls_verify_code == 20
    with pytest.raises(ValidationError):
        Measurement(**{**fields, "kind": "dns"})
    with pytest.raises(ValidationError):
        Measurement(**{**fields, "status": "success"})
