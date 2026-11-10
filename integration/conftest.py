"""Explicit disposable PostgreSQL fixture shared by runtime integration tests."""

import os

import pytest
from sqlalchemy.engine import make_url

from service.database import database
from service.schema import upgrade


@pytest.fixture
def postgres():
    raw = os.environ.get("NETGUARDIAN_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Disposable PostgreSQL test database is not configured")
    url = make_url(raw)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.database != "netguardian_test"
    ):
        pytest.fail("Use a loopback PostgreSQL database named netguardian_test")
    upgrade(raw)
    engine, sessions = database(raw)
    try:
        yield engine, sessions
    finally:
        engine.dispose()
