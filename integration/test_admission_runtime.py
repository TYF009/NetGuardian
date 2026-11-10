"""Verify the default admission concurrency ceiling through real loopback HTTP."""

import asyncio
import socket

import httpx
import uvicorn

from service.api import create_app
from service.schema import upgrade
from service.settings import Settings


def test_real_http_concurrency_limit_and_recovery(tmp_path):
    async def scenario():
        url = f"sqlite:///{tmp_path / 'admission.db'}"
        upgrade(url)
        app = create_app(Settings(url, {"a" * 32: "one"}, {}))
        entered = 0
        saturated = asyncio.Event()
        release = asyncio.Event()

        @app.get("/api/_admission_fixture")
        async def held_request():
            nonlocal entered
            entered += 1
            if entered == 32:
                saturated.set()
            await release.wait()
            return {"fixture": "released"}

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="error",
                access_log=False,
                timeout_graceful_shutdown=2,
            )
        )
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        requests = []
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if server_task.done():
                        await server_task
                        raise AssertionError("Fixture server did not start")
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}",
                trust_env=False,
                timeout=10,
                limits=httpx.Limits(max_connections=64),
            ) as client:
                requests = [
                    asyncio.create_task(client.get("/api/_admission_fixture")) for _ in range(32)
                ]
                await asyncio.wait_for(saturated.wait(), timeout=10)
                rejected = await asyncio.gather(
                    *(
                        client.get("/api/targets", headers={"Authorization": "Bearer " + "a" * 32})
                        for _ in range(8)
                    )
                )
                assert all(response.status_code == 429 for response in rejected)
                assert all(response.headers["retry-after"] == "1" for response in rejected)
                assert entered == 32
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/ready")).status_code == 200
                release.set()
                finished = await asyncio.gather(*requests)
                assert all(response.status_code == 200 for response in finished)
                recovered = await client.get(
                    "/api/targets", headers={"Authorization": "Bearer " + "a" * 32}
                )
                assert recovered.status_code == 200
                assert recovered.json()["origins"] == []
        finally:
            release.set()
            await asyncio.gather(*requests, return_exceptions=True)
            server.should_exit = True
            await asyncio.wait_for(server_task, timeout=5)
            listener.close()
            app.state.sessions.kw["bind"].dispose()

    asyncio.run(scenario())
