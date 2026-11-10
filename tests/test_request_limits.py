"""ASGI request limits reject bodies before handing them to the application."""

import asyncio

import pytest

from service.api import create_app
from service.request_limits import RequestBodyLimit
from service.schema import upgrade
from service.settings import Settings


@pytest.mark.parametrize("size,allowed", [(65536, True), (65537, False)])
def test_chunked_body_limit_without_content_length(size, allowed):
    async def scenario():
        chunks = [b"x" * 32768, b"x" * (size - 32768)]
        sent, received = [], []

        async def receive():
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}

        async def send(message):
            sent.append(message)

        async def app(scope, receive, send):
            received.append(await receive())

        await RequestBodyLimit(app)({"type": "http"}, receive, send)
        if allowed:
            assert len(received[0]["body"]) == size
        else:
            assert received == []
            assert sent[0]["status"] == 413

    asyncio.run(scenario())


def test_slow_body_times_out_before_application():
    async def scenario():
        sent = []

        async def receive():
            await asyncio.sleep(1)
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)

        async def app(*args):
            pytest.fail("Incomplete body reached application")

        await RequestBodyLimit(app, receive_seconds=0.01)({"type": "http"}, receive, send)
        assert sent[0]["status"] == 408

    asyncio.run(scenario())


def test_api_installs_request_body_limit(tmp_path):
    from fastapi.testclient import TestClient

    settings = Settings(f"sqlite:///{tmp_path / 'body-limit.db'}", {"a" * 32: "one"}, {})
    upgrade(settings.database_url)
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/jobs",
        content=b"x" * 65537,
        headers={"Authorization": "Bearer " + "a" * 32, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
