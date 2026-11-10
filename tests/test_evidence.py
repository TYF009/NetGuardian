"""Report claims cite stored evidence and comparisons refuse incompatible observations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from probe_core.contracts import Measurement, Timings
from service.api import create_app
from service.database import Incident, Job, Monitor
from service.evidence import compare
from service.schema import upgrade
from service.settings import Settings


def sample():
    return Measurement(
        job_id=uuid4(),
        attempt=1,
        kind="http",
        vantage_id=uuid4(),
        target="https://example.com/?token=secret",
        configuration_hash="a" * 64,
        observed_at=datetime.now(UTC),
        probe_version="test",
        policy_version="v1",
        status="success",
        resolved_ips=("8.8.8.8",),
        connected_ip="8.8.8.8",
        timings=Timings(http_total_ms=10),
        http_status=503,
    )


def test_comparison_rejects_skew_and_different_configuration():
    left = sample()
    right = left.model_copy(
        update={"job_id": uuid4(), "vantage_id": uuid4(), "timings": Timings(http_total_ms=20)}
    )
    assert compare(left, right)["right_minus_left_ms"]["http_total_ms"] == 10
    assert not compare(left, left)["comparable"]
    assert not compare(left, right.model_copy(update={"configuration_hash": "b" * 64}))[
        "comparable"
    ]
    assert not compare(
        left, right.model_copy(update={"observed_at": left.observed_at + timedelta(seconds=31)})
    )["comparable"]


def test_report_snapshot_redaction_and_isolation(tmp_path):
    settings = Settings(
        f"sqlite:///{tmp_path / 'evidence.db'}", {"a" * 32: "one", "b" * 32: "two"}, {}
    )
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    result = sample()
    with app.state.sessions.begin() as session:
        session.add(
            Job(
                id=str(result.job_id),
                workspace="one",
                kind="http",
                target=result.target,
                policy_version="v1",
                state="succeeded",
                result=result.model_dump(mode="json"),
            )
        )
        monitor = Monitor(
            id=str(uuid4()), workspace="one", name="Fixture", kind="http", target=result.target
        )
        session.add(monitor)
        incident = Incident(workspace="one", monitor_id=monitor.id, evidence=[str(result.job_id)])
        session.add(incident)
        session.flush()
        incident_id = incident.id
    one = {"Authorization": "Bearer " + "a" * 32}
    two = {"Authorization": "Bearer " + "b" * 32}
    assert (
        client.post("/api/reports", headers=two, json={"incident_id": incident_id}).status_code
        == 404
    )
    response = client.post("/api/reports", headers=one, json={"incident_id": incident_id})
    assert response.status_code == 201
    report_id = response.json()["id"]
    listed = client.get("/api/reports", headers=one).json()
    assert len(listed) == 1 and listed[0]["id"] == report_id
    assert listed[0]["incident_id"] == incident_id
    assert "snapshot" not in listed[0]
    assert client.get("/api/reports", headers=two).json() == []
    unavailable = client.post("/api/investigations", headers=one, json={"report_id": report_id})
    assert unavailable.status_code == 201
    assert unavailable.json()["output"]["status"] == "unavailable"
    audit = client.get("/api/audit-events", headers=one).json()
    assert {event["action"] for event in audit} == {"report.created", "investigation.created"}

    assert (
        client.post("/api/investigations", headers=two, json={"report_id": report_id}).status_code
        == 404
    )
    investigation_id = unavailable.json()["id"]
    history = client.get("/api/investigations", headers=one).json()
    assert len(history) == 1
    assert history[0]["id"] == investigation_id
    assert history[0]["report_id"] == report_id
    assert "output" not in history[0]
    assert client.get("/api/investigations", headers=two).json() == []
    investigation_path = f"/api/investigations/{investigation_id}"
    assert client.get(investigation_path, headers=two).status_code == 404
    detail = client.get(investigation_path, headers=one).json()
    assert detail["output"] == unavailable.json()["output"]
    assert detail["evidence_hash"] == unavailable.json()["evidence_hash"]
    restarted = TestClient(create_app(settings))
    assert restarted.get(investigation_path, headers=one).json() == detail
    saved = client.get(f"/api/reports/{report_id}", headers=one).json()
    assert saved["integrity"] == "verified"
    assert "secret" not in str(saved)
    assert saved["snapshot"]["claims"][0]["evidence_ids"] == [str(result.job_id)]
    claim = saved["snapshot"]["claims"][0]["text"]
    assert "probe execution status: success" in claim
    assert "HTTP response status: 503" in claim
    assert "does not imply application health" in claim
    assert client.get(f"/api/reports/{report_id}", headers=two).status_code == 404
    with app.state.sessions.begin() as session:
        session.get(Job, str(result.job_id)).result = None
    assert client.get(f"/api/reports/{report_id}", headers=one).json() == saved


def test_corrupted_report_cannot_be_read_or_investigated(tmp_path):
    from service.database import Report
    from service.evidence import snapshot_hash

    settings = Settings(f"sqlite:///{tmp_path / 'corrupt.db'}", {"a" * 32: "one"}, {})
    upgrade(settings.database_url)
    app = create_app(settings)
    client = TestClient(app)
    auth = {"Authorization": "Bearer " + "a" * 32}
    snapshot = {"evidence": [], "claims": []}
    with app.state.sessions.begin() as session:
        monitor = Monitor(
            id=str(uuid4()),
            workspace="one",
            name="Fixture",
            kind="dns",
            target="https://example.com",
        )
        incident = Incident(id=str(uuid4()), workspace="one", monitor_id=monitor.id, evidence=[])
        session.add_all([monitor, incident])
        record = Report(
            workspace="one",
            incident_id=incident.id,
            snapshot=snapshot,
            content_hash=snapshot_hash(snapshot),
        )
        session.add(record)
        session.flush()
        report_id = record.id
    assert client.get(f"/api/reports/{report_id}", headers=auth).status_code == 200
    with app.state.sessions.begin() as session:
        record = session.get(Report, report_id)
        record.snapshot = {"evidence": [], "claims": ["Unrecorded claim"]}
    assert client.get(f"/api/reports/{report_id}", headers=auth).status_code == 409
    assert (
        client.post("/api/investigations", headers=auth, json={"report_id": report_id}).status_code
        == 409
    )
    assert client.get("/api/investigations", headers=auth).json() == []


def test_http_comparison_does_not_leak_dns_delta():
    left = sample().model_copy(update={"timings": Timings(dns_lookup_ms=2, http_total_ms=10)})
    right = left.model_copy(
        update={
            "job_id": uuid4(),
            "vantage_id": uuid4(),
            "timings": Timings(dns_lookup_ms=5, http_total_ms=20),
        }
    )
    result = compare(left, right)
    assert result["comparable"] is True
    assert result["right_minus_left_ms"] == {"http_total_ms": 10}
    assert result["metric_limitations"]


def test_non_http_claim_does_not_invent_response_status():
    from service.evidence import observation_claim

    claim = observation_claim({"job_id": "fixture", "kind": "dns", "status": "error"})
    assert claim == {
        "text": "Recorded dns probe execution status: error.",
        "evidence_ids": ["fixture"],
    }
