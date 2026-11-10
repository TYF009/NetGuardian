"""Admission limits run before body reads and never allocate per-attacker keys."""

import asyncio

from service.rate_limits import RequestAdmission


def test_mutation_buckets_are_shared_by_workspace_and_refill():
    async def scenario():
        now = [0.0]
        accepted, statuses = [], []

        async def app(scope, receive, send):
            accepted.append(scope["path"])

        async def receive():
            raise AssertionError("Rejected requests must not read a body")

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])

        limiter = RequestAdmission(
            app, {"a": "one", "b": "one", "c": "two"}, clock=lambda: now[0], mutation_burst=1
        )

        async def request(token, path="/api/reports", method="POST"):
            await limiter(
                {
                    "type": "http",
                    "path": path,
                    "method": method,
                    "headers": [(b"authorization", b"Bearer " + token)],
                },
                receive,
                send,
            )

        await request(b"a")
        await request(b"b")  # Same workspace, another token does not evade its limit.
        await request(b"c")
        await request(b"unknown1")
        await request(b"unknown2")
        assert statuses == [429, 429]
        assert len(limiter.mutations) == 3
        now[0] = 1.0
        await request(b"b")
        await request(b"b", "/health", "GET")
        assert len(accepted) == 5
        assert limiter.active == 0

    asyncio.run(scenario())


def test_concurrency_is_released_after_cancellation_and_health_bypasses():
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        statuses = []

        async def app(scope, receive, send):
            if scope["path"] == "/api/jobs":
                entered.set()
                await release.wait()

        async def receive():
            raise AssertionError("No body read expected")

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])

        limiter = RequestAdmission(app, {}, max_active=1)
        scope = {"type": "http", "path": "/api/jobs", "method": "GET"}
        pending = asyncio.create_task(limiter(scope, receive, send))
        await entered.wait()
        await limiter(scope, receive, send)
        await limiter({**scope, "path": "/ready"}, receive, send)
        assert statuses == [429]
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        assert limiter.active == 0
        release.set()
        await limiter(scope, receive, send)
        assert statuses == [429]

    asyncio.run(scenario())


def test_global_budget_also_limits_unknown_readers():
    async def scenario():
        called, statuses = [], []

        async def app(scope, receive, send):
            called.append(scope)

        async def receive():
            raise AssertionError("No body expected")

        async def send(message):
            if message["type"] == "http.response.start":
                statuses.append(message["status"])
                assert (b"retry-after", b"1") in message["headers"]

        limiter = RequestAdmission(app, {}, clock=lambda: 0, burst=1)
        scope = {"type": "http", "path": "/api/jobs", "method": "GET"}
        await limiter(scope, receive, send)
        await limiter(scope, receive, send)
        assert len(called) == 1 and statuses == [429]

    asyncio.run(scenario())
