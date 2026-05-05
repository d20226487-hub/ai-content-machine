"""Distributed per-provider rate limiting backed by Redis.

Why Redis: every Celery worker (and any other process that calls a provider)
shares the same throttle. A token bucket / sliding window in process memory
would let workers stampede past the configured limits.

Three controls per provider:
  * max_concurrency  — at most N requests in flight at any moment
  * requests_per_minute — sliding-window cap over the last 60s
  * inter_request_delay_ms — fixed sleep AFTER acquiring (helps with bursty providers)

Usage:
    limiter = get_rate_limiter()
    async with limiter.acquire(provider_code, max_concurrency=5,
                               requests_per_minute=60, inter_request_delay_ms=0):
        ... call the provider ...
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import random
import time
import uuid

import redis.asyncio as redis_async


_KEY_PREFIX = "rl:"
# Conservative ceiling on how long any single acquire is allowed to block waiting
# for capacity. Beyond this we give up so the task surfaces an error to the user
# rather than hanging forever.
_MAX_WAIT_SECONDS = 300.0


# Atomic concurrency-slot acquire. EVAL runs single-threaded in Redis, so the
# SCARD and SADD pair below cannot interleave with another worker's check —
# the previous "SCARD then SADD then SCARD" sequence allowed N workers to all
# observe count<max simultaneously, all SADD their tokens, and end up briefly
# at count=N+max-1. The Lua version makes "check + claim" indivisible.
#
# KEYS[1] — the conc set key. ARGV[1] — max concurrency. ARGV[2] — token.
# ARGV[3] — TTL seconds (re-applied each call so a stuck token gets reaped).
# Returns 1 on success, 0 on full.
_CONC_ACQUIRE_LUA = """
local key = KEYS[1]
local max = tonumber(ARGV[1])
local token = ARGV[2]
local ttl = tonumber(ARGV[3])
redis.call('EXPIRE', key, ttl)
local cur = redis.call('SCARD', key)
if cur < max then
  redis.call('SADD', key, token)
  return 1
end
return 0
"""


# Atomic sliding-window RPM acquire. Same single-threaded EVAL guarantee:
# zremrangebyscore (prune old) → zcard → conditional zadd happen as one unit.
# If full, returns the oldest score so the caller knows when to wake up.
#
# KEYS[1] — the rpm sorted-set key.
# ARGV[1] — RPM cap. ARGV[2] — now (float seconds). ARGV[3] — cutoff (now-60).
# ARGV[4] — unique member to insert on success. ARGV[5] — TTL seconds.
# Returns: {1, 0} on acquire; {0, oldest_score} on full.
_RPM_ACQUIRE_LUA = """
local key = KEYS[1]
local cap = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local cutoff = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = tonumber(redis.call('ZCARD', key))
if count < cap then
  redis.call('ZADD', key, now, member)
  redis.call('EXPIRE', key, ttl)
  return {1, '0'}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
if #oldest >= 2 then
  return {0, oldest[2]}
end
return {0, '0'}
"""


class ProviderRateLimiter:
    """A new Redis client is opened per `acquire()` because Celery tasks each
    spin up a fresh asyncio loop (via `asyncio.run`); reusing a client across
    loops yields the classic "Future attached to a different loop" error.
    The connect cost (~1ms to local Redis) is irrelevant compared to a model call.
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url

    @contextlib.asynccontextmanager
    async def acquire(
        self,
        *,
        provider_code: str,
        max_concurrency: int,
        requests_per_minute: int,
        inter_request_delay_ms: int = 0,
    ):
        r = redis_async.from_url(self._redis_url, decode_responses=True)
        slot_token: str | None = None
        try:
            slot_token = await self._acquire_concurrency(r, provider_code, max_concurrency)
            await self._wait_for_rpm(r, provider_code, requests_per_minute)
            if inter_request_delay_ms > 0:
                await asyncio.sleep(inter_request_delay_ms / 1000.0)
            yield
        finally:
            if slot_token is not None:
                try:
                    await self._release_concurrency(r, provider_code, slot_token)
                except Exception:
                    pass  # crashed; the TTL on the conc set will free it
            await r.aclose()

    # ---- concurrency: a Redis SET of in-flight slot tokens ----

    async def _acquire_concurrency(
        self, r: redis_async.Redis, code: str, max_c: int
    ) -> str:
        key = f"{_KEY_PREFIX}conc:{code}"
        token = uuid.uuid4().hex
        deadline = time.monotonic() + _MAX_WAIT_SECONDS
        while True:
            ok = await r.eval(_CONC_ACQUIRE_LUA, 1, key, max_c, token, 600)
            if int(ok) == 1:
                return token
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting {int(_MAX_WAIT_SECONDS)}s for concurrency slot on '{code}'"
                )
            await asyncio.sleep(0.1 + random.random() * 0.3)

    async def _release_concurrency(
        self, r: redis_async.Redis, code: str, token: str
    ) -> None:
        await r.srem(f"{_KEY_PREFIX}conc:{code}", token)

    # ---- RPM: sliding window of timestamps in a sorted set ----

    async def _wait_for_rpm(
        self, r: redis_async.Redis, code: str, rpm: int
    ) -> None:
        if rpm <= 0:
            return  # unconfigured / unlimited
        key = f"{_KEY_PREFIX}rpm:{code}"
        deadline = time.monotonic() + _MAX_WAIT_SECONDS
        while True:
            now = time.time()
            cutoff = now - 60.0
            member = f"{now}:{uuid.uuid4().hex}"
            result = await r.eval(
                _RPM_ACQUIRE_LUA, 1, key, rpm, now, cutoff, member, 120
            )
            ok, oldest_score = int(result[0]), float(result[1] or 0.0)
            if ok == 1:
                return
            # Over the limit — sleep until the oldest entry ages out (capped).
            if oldest_score > 0:
                wait = (oldest_score + 60.0) - now + 0.05
                await asyncio.sleep(max(0.05, min(wait, 5.0)))
            else:
                await asyncio.sleep(0.2)
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting {int(_MAX_WAIT_SECONDS)}s for RPM slot on '{code}'"
                )


_singleton: ProviderRateLimiter | None = None


def get_rate_limiter() -> ProviderRateLimiter:
    """Process-wide singleton. The Celery task and the API both use the same instance."""
    global _singleton
    if _singleton is None:
        url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        _singleton = ProviderRateLimiter(url)
    return _singleton
