"""Reject malformed administrator settings and non-ASCII authentication input."""

import json

import pytest

from service.settings import Settings


@pytest.mark.parametrize("tokens", [[], {}, {"short": "one"}, {"a" * 32: 42}, {"文" * 32: "one"}])
def test_invalid_credentials(monkeypatch, tokens):
    monkeypatch.setenv("NETGUARDIAN_TOKENS", json.dumps(tokens))
    with pytest.raises(ValueError):
        Settings.from_environment()


def test_unknown_workspace_origin_policy(monkeypatch):
    monkeypatch.setenv("NETGUARDIAN_TOKENS", json.dumps({"a" * 32: "one"}))
    monkeypatch.setenv("NETGUARDIAN_ORIGINS", json.dumps({"two": ["https://example.com"]}))
    with pytest.raises(ValueError):
        Settings.from_environment()
