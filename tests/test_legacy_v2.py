"""Legacy opt-in uses authenticated durable jobs, never direct target execution."""

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import legacy_v2
from probe_core.policy import CloudPolicy
from service.api import create_app
from service.schema import upgrade
from service.settings import Settings
from service.worker import run_once


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.com",
        "http://localhost",
        "https://u:p@example.com",
        "https://@example.com",
        "https://example.com/path",
        "https://example.com?token=x",
        "http://127.0.0.1:0",
    ],
)
def test_control_origin_rejected(origin):
    with pytest.raises(ValueError):
        legacy_v2.V2Client(origin, "a" * 32)


@pytest.mark.parametrize(
    "status,headers,body",
    [
        (302, {"location": "http://169.254.169.254"}, b""),
        (200, {"content-encoding": "gzip"}, b"x"),
        (200, {}, b"x" * 262145),
    ],
)
def test_response_boundaries(status, headers, body):
    seen = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body

    def handler(request):
        seen.append(request.url)
        return httpx.Response(status, headers=headers, stream=Stream())

    client = legacy_v2.V2Client(
        "http://127.0.0.1:8000", "a" * 32, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ValueError):
        client.targets()
    assert len(seen) == 1


def test_ui_queues_persistent_job_and_disconnects(tmp_path, monkeypatch):
    settings = Settings(
        f"sqlite:///{tmp_path / 'legacy.db'}",
        {"a" * 32: "one"},
        {"one": CloudPolicy("v1", frozenset({("8.8.8.8", 443, "https")}))},
    )
    upgrade(settings.database_url)
    backend = create_app(settings)
    real_client = legacy_v2.V2Client
    monkeypatch.setattr(
        legacy_v2,
        "V2Client",
        lambda origin, token: real_client(
            origin, token, transport=httpx.ASGITransport(app=backend)
        ),
    )
    monkeypatch.setenv("NETGUARDIAN_STREAMLIT_V2", "true")
    monkeypatch.setenv("NETGUARDIAN_API_URL", "http://127.0.0.1:8000")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()

    def button(label):
        return next(item for item in app.button if item.label == label)

    app.text_input[0].set_value("a" * 32)
    button("Connect to V2").click().run()
    assert not app.exception
    app.selectbox[0].select("https://8.8.8.8:443")
    button("Queue V2 diagnostic").click().run()
    assert not app.exception
    jobs = real_client(
        "http://127.0.0.1:8000", "a" * 32, transport=httpx.ASGITransport(app=backend)
    ).jobs()
    assert len(jobs) == 1 and jobs[0].state == "queued"
    app.selectbox[2].select(jobs[0].id).run()
    button("Inspect / refresh V2 result").click().run()
    assert any("No measurement recorded" in item.value for item in app.info)
    # The real shared executor handles an IP-literal DNS job without network traffic.
    assert asyncio.run(run_once(backend.state.sessions, settings.policies, vantage_id=uuid4()))
    button("Inspect / refresh V2 result").click().run()
    assert not app.exception
    assert len(app.json) == 1
    result = (
        real_client("http://127.0.0.1:8000", "a" * 32, transport=httpx.ASGITransport(app=backend))
        .detail(jobs[0].id)
        .result
    )
    assert result.status == "success" and result.dns.used_dns is False
    assert result.timings.dns_lookup_ms is None and result.received_at is not None
    button("Disconnect V2").click().run()
    assert not app.exception
    assert app.text_input[0].value == ""
    assert len(app.selectbox) == 0
