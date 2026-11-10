"""Opt-in real local model workflow using an existing verified evidence export."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from service.api import create_app
from service.database import Incident, Monitor, Report
from service.report_files import load_export
from service.schema import upgrade
from service.settings import Settings


def test_real_model_investigation_persists_and_is_tenant_scoped(tmp_path, monkeypatch):
    report_path = os.environ.get("NETGUARDIAN_TEST_MODEL_REPORT")
    if not report_path:
        pytest.skip("Set NETGUARDIAN_TEST_MODEL_REPORT to an existing evidence export")
    exported = load_export(Path(report_path))
    snapshot = exported["snapshot"]
    assert snapshot["evidence"], "Real recorded evidence is required"
    monkeypatch.setenv(
        "NETGUARDIAN_OLLAMA_URL",
        os.environ.get("NETGUARDIAN_TEST_MODEL_URL", "http://127.0.0.1:11434"),
    )
    monkeypatch.setenv(
        "NETGUARDIAN_OLLAMA_MODEL", os.environ.get("NETGUARDIAN_TEST_MODEL", "qwen2.5:1.5b")
    )
    settings = Settings(
        f"sqlite:///{tmp_path / 'model.db'}", {"a" * 32: "one", "b" * 32: "two"}, {}
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    with app.state.sessions.begin() as session:
        monitor = Monitor(
            id=str(uuid4()),
            workspace="one",
            name="Imported evidence validation",
            kind="http",
            target="https://example.com",
            enabled=0,
        )
        incident = Incident(
            id=snapshot["incident_id"],
            workspace="one",
            monitor_id=monitor.id,
            state=snapshot["state"],
            evidence=[],
        )
        report = Report(
            id=str(uuid4()),
            workspace="one",
            incident_id=incident.id,
            snapshot=snapshot,
            content_hash=exported["content_hash"],
        )
        session.add_all([monitor, incident, report])
        report_id = report.id
    one = {"Authorization": "Bearer " + "a" * 32}
    two = {"Authorization": "Bearer " + "b" * 32}
    with TestClient(app) as client:
        response = client.post("/api/investigations", headers=one, json={"report_id": report_id})
        assert response.status_code == 201
        investigation = response.json()
        assert investigation["output"]["status"] == "validated", investigation["output"]
        assert investigation["output"]["facts"], "Empty findings do not pass the model gate"
        path = f"/api/investigations/{investigation['id']}"
        saved = client.get(path, headers=one).json()
        assert saved["evidence_hash"] == exported["content_hash"]
        assert client.get(path, headers=two).status_code == 404
        assert len(client.get("/api/investigations", headers=one).json()) == 1
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path, headers=one).json() == saved
