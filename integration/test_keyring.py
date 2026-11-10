"""Explicit opt-in OS credential-store round trip using an isolated temporary item."""

import os
import secrets
from uuid import uuid4

import pytest

from agent.client import secure_keyring


@pytest.mark.skipif(
    os.environ.get("NETGUARDIAN_TEST_KEYRING") != "true",
    reason="Explicit OS-keyring integration opt-in required",
)
def test_os_keyring_round_trip_and_cleanup():
    store = secure_keyring()
    service = "NetGuardian-integration-" + str(uuid4())
    account = "temporary-test-account"
    credential = secrets.token_urlsafe(32)
    written = False
    try:
        assert store.get_password(service, account) is None
        store.set_password(service, account, credential)
        written = True
        retrieved = store.get_password(service, account)
        assert retrieved is not None
        assert secrets.compare_digest(retrieved, credential)
    finally:
        if written:
            store.delete_password(service, account)
    assert store.get_password(service, account) is None
