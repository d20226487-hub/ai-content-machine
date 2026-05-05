"""Smoke tests for the login throttle.

We can't unit-test "raise 429 from the route" without spinning up the full
FastAPI app + DB; what we can test is the Redis state machine in isolation.
The throttle module opens a Redis client per call and is fail-open on
errors — both of those properties are exercised here with a fakeredis-style
in-memory shim.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeRedis:
    """Minimal in-memory shim for the four redis-asyncio methods we use."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.expiry: dict[str, int] = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, *, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = str(v)
        if ex is not None:
            self.expiry[k] = ex
        return True

    async def incr(self, k):
        cur = int(self.store.get(k, 0))
        cur += 1
        self.store[k] = str(cur)
        return cur

    async def delete(self, k):
        self.store.pop(k, None)
        self.expiry.pop(k, None)

    async def ttl(self, k):
        return self.expiry.get(k, -1)

    async def aclose(self):
        pass


def _patch_redis(fake: _FakeRedis):
    """Make ``redis_async.from_url(...)`` return our fake."""
    return patch(
        "app.services.login_throttle.redis_async.from_url",
        MagicMock(return_value=fake),
    )


@pytest.mark.asyncio
async def test_check_allows_when_no_history():
    from app.services import login_throttle

    fake = _FakeRedis()
    with _patch_redis(fake):
        v = await login_throttle.check(ip="1.2.3.4", email="a@b.c")
    assert v.allowed is True
    assert v.reason == "ok"


@pytest.mark.asyncio
async def test_email_lockout_kicks_in_at_cap():
    from app.services import login_throttle

    fake = _FakeRedis()
    with _patch_redis(fake):
        for _ in range(login_throttle.EMAIL_MAX_FAILURES):
            await login_throttle.record_failure(ip="1.2.3.4", email="a@b.c")
        v = await login_throttle.check(ip="1.2.3.4", email="a@b.c")
    assert v.allowed is False
    assert v.reason == "email"
    assert v.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_ip_lockout_kicks_in_for_distributed_user_attempts():
    """Same IP brute-forcing many emails — IP cap must catch this.

    The email counters never reach their cap because the attacker rotates
    addresses. Only the IP counter accumulates.
    """
    from app.services import login_throttle

    fake = _FakeRedis()
    with _patch_redis(fake):
        for i in range(login_throttle.IP_MAX_FAILURES):
            await login_throttle.record_failure(
                ip="1.2.3.4", email=f"victim{i}@example.com"
            )
        v = await login_throttle.check(ip="1.2.3.4", email="anyone@example.com")
    assert v.allowed is False
    assert v.reason == "ip"


@pytest.mark.asyncio
async def test_email_canonicalized_lowercase():
    """A@B.c and a@b.c must share a counter."""
    from app.services import login_throttle

    fake = _FakeRedis()
    with _patch_redis(fake):
        for _ in range(login_throttle.EMAIL_MAX_FAILURES):
            await login_throttle.record_failure(ip="1.2.3.4", email="A@B.C")
        v = await login_throttle.check(ip="9.9.9.9", email="a@b.c")
    assert v.allowed is False
    assert v.reason == "email"


@pytest.mark.asyncio
async def test_reset_email_clears_counter_only_for_that_user():
    """Successful login clears the email counter, not the IP counter.

    Otherwise an attacker on a shared NAT could rotate accounts and reset the
    IP cap on each successful guess.
    """
    from app.services import login_throttle

    fake = _FakeRedis()
    with _patch_redis(fake):
        for _ in range(login_throttle.IP_MAX_FAILURES - 1):
            await login_throttle.record_failure(ip="1.2.3.4", email="a@b.c")
        await login_throttle.reset_email("a@b.c")
        # Email counter should be gone, IP counter should still be there.
        assert "login_fail:email:a@b.c" not in fake.store
        assert fake.store.get("login_fail:ip:1.2.3.4") == str(
            login_throttle.IP_MAX_FAILURES - 1
        )


@pytest.mark.asyncio
async def test_check_fails_open_when_redis_down():
    """If Redis is unreachable, login still works.

    Losing rate-limiting briefly is much better than locking everyone out.
    """
    from app.services import login_throttle

    with patch(
        "app.services.login_throttle.redis_async.from_url",
        MagicMock(side_effect=RuntimeError("redis down")),
    ):
        v = await login_throttle.check(ip="1.2.3.4", email="a@b.c")
    assert v.allowed is True
    assert v.reason == "ok"


@pytest.mark.asyncio
async def test_record_failure_does_not_raise_when_redis_down():
    """record_failure must never propagate — auth must keep working."""
    from app.services import login_throttle

    with patch(
        "app.services.login_throttle.redis_async.from_url",
        MagicMock(side_effect=RuntimeError("redis down")),
    ):
        await login_throttle.record_failure(ip="1.2.3.4", email="a@b.c")  # no raise
