"""Untrusted model bodies are bounded before decoding or decompression."""

import asyncio
import json

import httpx
import pytest

from service.investigation import ask_ollama


@pytest.mark.parametrize("case", ["valid", "oversized", "compressed", "tools"])
def test_model_transport_response_boundaries(monkeypatch, case):
    read_chunks = []
    closed = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if case == "compressed":
                raise AssertionError("Compressed bytes must not be consumed")
            if case == "oversized":
                for chunk in (b"x" * 65536, b"x", b"must-not-read"):
                    read_chunks.append(len(chunk))
                    yield chunk
            else:
                message = {"content": '{"facts":[],"hypotheses":[]}'}
                if case == "tools":
                    message["tool_calls"] = [{"function": {"name": "shell"}}]
                yield json.dumps({"message": message}).encode()

        async def aclose(self):
            closed.append(True)

    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        assert request.url.path == "/api/chat"
        body = json.loads(request.content)
        assert body["stream"] is False
        return httpx.Response(
            200,
            stream=Stream(),
            headers={"Content-Encoding": "gzip"} if case == "compressed" else {},
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "service.investigation.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    if case == "valid":
        assert (
            asyncio.run(ask_ollama("http://127.0.0.1:11434", "fixture", []))
            == '{"facts":[],"hypotheses":[]}'
        )
    else:
        with pytest.raises(ValueError):
            asyncio.run(ask_ollama("http://127.0.0.1:11434", "fixture", []))
    assert closed
    if case == "oversized":
        assert read_chunks == [65536, 1]
