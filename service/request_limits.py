"""Bound request buffering before JSON parsing, including chunked bodies."""

import asyncio

from starlette.responses import JSONResponse


class RequestBodyLimit:
    def __init__(self, app, max_bytes=65536, receive_seconds=10):
        self.app = app
        self.max_bytes = max_bytes
        self.receive_seconds = receive_seconds

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content = bytearray()
        try:
            async with asyncio.timeout(self.receive_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(content) + len(chunk) > self.max_bytes:
                        await JSONResponse(
                            {"detail": "Request body exceeds 64 KiB limit"}, status_code=413
                        )(scope, receive, send)
                        return
                    content.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await JSONResponse(
                {"detail": "Request body receive deadline exceeded"}, status_code=408
            )(scope, receive, send)
            return

        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(content), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)
