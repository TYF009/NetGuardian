"""Readiness differs from process liveness and does not expose DB diagnostics."""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from service.api import create_app
from service.schema import upgrade
from service.settings import Settings


def test_readiness_database_failure_and_recovery(tmp_path, monkeypatch):
    settings = Settings(f"sqlite:///{tmp_path / 'ready.db'}", {"a" * 32: "one"}, {})
    upgrade(settings.database_url)
    client = TestClient(create_app(settings))
    assert client.get("/ready").json()["schema"] == "current"

    def unavailable(engine):
        raise OperationalError("private database detail", {}, Exception("secret"))

    with monkeypatch.context() as patch:
        patch.setattr("service.api.require_schema", unavailable)
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
        assert response.status_code == 503
        assert "secret" not in response.text and "private" not in response.text
    assert client.get("/ready").status_code == 200
