"""Shared configuration identities preserve comparison semantics."""

from uuid import uuid4

import pytest

from probe_core.contracts import ProbeRequest, configuration_hash


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "tcp"},
        {"target": "https://example.com/other"},
        {"deadline_ms": 5000},
        {"policy_version": "v2"},
    ],
)
def test_configuration_identity_includes_measurement_settings(changes):
    request = ProbeRequest(
        job_id=uuid4(), kind="http", target="https://example.com", policy_version="v1"
    )
    assert configuration_hash(request) == configuration_hash(
        request.model_copy(update={"job_id": uuid4()})
    )
    assert configuration_hash(request) != configuration_hash(request.model_copy(update=changes))
