from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import diagnostics


@pytest.mark.parametrize(
    "target",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1",
        "http://[::1]",
        "https://example.com",
        "host & whoami",
        "-h 100",
    ],
)
def test_probe_entry_points_fail_closed(target):
    for name in (
        "get_ping_latency",
        "get_http_request_duration",
        "check_http_status",
        "check_port",
        "get_dns_info",
        "run_traceroute",
        "get_public_ip",
        "get_ip_info",
        "get_local_info",
    ):
        result = getattr(diagnostics, name)(target)
        assert result.status == "disabled"
        assert result.http_request_ms is None


def test_measurement_labels():
    assert diagnostics.format_http_duration(diagnostics.ProbeResult("success", 0)) == "0.00 ms"
    assert diagnostics.format_http_duration(diagnostics.ProbeResult("error")) == "Error"
    assert diagnostics.format_http_duration(diagnostics.ProbeResult("timeout")) == "Timeout"
    assert diagnostics.format_http_duration(diagnostics.ProbeResult()) == "Disabled"


def test_app_empty_selection_and_reruns():
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
    ).run()
    assert not app.exception
    assert not app.metric
    assert all(button.disabled for button in app.button)
    app.sidebar.multiselect[0].select("GitHub").run()
    assert not app.exception
    assert app.metric[0].value == "Disabled"
    app.sidebar.multiselect[0].set_value([]).run()
    assert not app.exception
    assert not app.metric


def test_framework_security_configuration():
    import tomllib

    import streamlit.config as config

    settings = tomllib.loads(Path(".streamlit/config.toml").read_text())
    assert settings["server"]["address"] == "127.0.0.1"
    assert settings["browser"]["gatherUsageStats"] is False
    assert config.get_option("server.enableCORS") is True
    assert config.get_option("server.enableXsrfProtection") is True
