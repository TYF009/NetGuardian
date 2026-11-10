"""Bounded process-local admission control, independent of database job quotas."""

import hashlib
import threading
import time

from starlette.responses import JSONResponse


class Bucket:
    def __init__(self, capacity, rate, now):
        self.capacity, self.rate = capacity, rate
        self.tokens, self.updated = float(capacity), now

    def take(self, now):
        self.tokens = min(self.capacity, self.tokens + max(0, now - self.updated) * self.rate)
        self.updated = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class RequestAdmission:
    def __init__(
        self,
        app,
        credentials,
        clock=time.monotonic,
        burst=120,
        rate=60,
        mutation_burst=60,
        mutation_rate=1,
        max_active=32,
    ):
        self.app, self.clock, self.max_active = app, clock, max_active
        self.identities = {
            hashlib.sha256(token.encode("ascii")).digest(): tenant
            for token, tenant in credentials.items()
        }
        now = clock()
        self.global_bucket = Bucket(burst, rate, now)
        # Only administrator-configured identities allocate buckets, never attacker input.
        self.mutations = {
            tenant: Bucket(mutation_burst, mutation_rate, now)
            for tenant in {*credentials.values(), None}
        }
        self.active = 0
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        auth = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"authorization"),
            b"",
        )
        tenant = None
        if auth.startswith(b"Bearer ") and len(auth) <= 4096:
            tenant = self.identities.get(hashlib.sha256(auth[7:]).digest())
        mutation = scope.get("method") not in {"GET", "HEAD", "OPTIONS"} and scope["path"] not in {
            "/api/agent/poll",
            "/api/agent/results",
        }
        with self.lock:
            now = self.clock()
            admitted = self.active < self.max_active and self.global_bucket.take(now)
            if admitted and mutation:
                admitted = self.mutations[tenant].take(now)
            if admitted:
                self.active += 1
        if not admitted:
            await JSONResponse(
                {"detail": "Control API request limit reached"},
                status_code=429,
                headers={"Retry-After": "1"},
            )(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            with self.lock:
                self.active -= 1
