"""Redis-backed throttle for /auth/login.

Two independent counters per attempt — one keyed on client IP, one on the
email being attempted. Both counters must be under their cap for the attempt
to proceed. Counters are incremented only on **failed** attempts; a
successful login resets the email counter so a legitimate user fat-fingering
their password three times doesn't get locked out forever after they finally
type it correctly.

Implementation: ``INCR + EXPIRE`` (fixed window, not sliding). The window is
small (minutes), so the imprecision at boundary moments is acceptable and
the implementation stays trivial. A sliding window would need a sorted set
with timestamp scores — fine, but unnecessary at this scale.

Why not slowapi: slowapi's middleware-style decorator is per-IP-only and
doesn't compose well with our `(ip, email)` two-key shape. A dozen lines
of Redis is simpler than the dependency.

The Redis client is opened per call to mirror the pattern in
``app.services.rate_limit`` (Celery tasks each spin up a fresh asyncio loop;
sharing a client across loops yields the classic "Future attached to a
different loop" error). This module is API-only today, so the constraint
doesn't bite — but keeping the pattern consistent saves a future foot-gun.
"""
from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as redis_async

from app.core.config import get_settings


# Tunables. Conservative defaults that won't punish a single user fixing a
# typo but make brute-forcing impractical from a single IP or against a
# single account. Office NAT is the main reason IP cap is generous.
IP_WINDOW_SECONDS = 5 * 60
IP_MAX_FAILURES = 30
EMAIL_WINDOW_SECONDS = 15 * 60
EMAIL_MAX_FAILURES = 10

_KEY_PREFIX = "login_fail:"


@dataclass
class ThrottleVerdict:
    allowed: bool
    retry_after_seconds: int  # 0 when allowed
    reason: str  # "ok" | "ip" | "email"


def _ip_key(ip: str) -> str:
    return f"{_KEY_PREFIX}ip:{ip}"


def _email_key(email: str) -> str:
    # Lowercase to canonicalize — same email different cases must share a counter.
    return f"{_KEY_PREFIX}email:{email.lower()}"


async def check(*, ip: str, email: str) -> ThrottleVerdict:
    """Return a verdict; never raises on Redis errors (fail-open by design).

    Fail-open: if Redis is down, login still works — losing rate-limiting is
    better than locking out everyone. Surface the issue via logs/metrics, not
    by killing auth.
    """
    settings = get_settings()
    try:
        client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            ip_count_str = await client.get(_ip_key(ip))
            email_count_str = await client.get(_email_key(email))
            ip_count = int(ip_count_str) if ip_count_str else 0
            email_count = int(email_count_str) if email_count_str else 0

            if email_count >= EMAIL_MAX_FAILURES:
                ttl = await client.ttl(_email_key(email))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after_seconds=max(int(ttl), 1) if ttl > 0 else EMAIL_WINDOW_SECONDS,
                    reason="email",
                )
            if ip_count >= IP_MAX_FAILURES:
                ttl = await client.ttl(_ip_key(ip))
                return ThrottleVerdict(
                    allowed=False,
                    retry_after_seconds=max(int(ttl), 1) if ttl > 0 else IP_WINDOW_SECONDS,
                    reason="ip",
                )
            return ThrottleVerdict(allowed=True, retry_after_seconds=0, reason="ok")
        finally:
            await client.aclose()
    except Exception:
        # Fail-open. We could log here; the API has an error_log path but we
        # don't want a Redis hiccup to flood it.
        return ThrottleVerdict(allowed=True, retry_after_seconds=0, reason="ok")


async def record_failure(*, ip: str, email: str) -> None:
    """Increment both counters and (re)set TTL on first occurrence in window.

    ``SET ... NX EX`` then ``INCR`` is the trick: the SET only takes if the
    key doesn't exist, which gives us the TTL exactly once per window.
    Subsequent INCRs increment in place without resetting the expiry.
    """
    settings = get_settings()
    try:
        client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            ip_k = _ip_key(ip)
            em_k = _email_key(email)
            await client.set(ip_k, 0, nx=True, ex=IP_WINDOW_SECONDS)
            await client.set(em_k, 0, nx=True, ex=EMAIL_WINDOW_SECONDS)
            await client.incr(ip_k)
            await client.incr(em_k)
        finally:
            await client.aclose()
    except Exception:
        # See note in check() — never raise from here.
        return


async def reset_email(email: str) -> None:
    """Clear the email-keyed failure counter on successful login.

    Why only the email counter and not the IP counter: leaving the IP counter
    in place keeps a malicious shared NAT from cycling through accounts and
    resetting the IP cap with each successful login.
    """
    settings = get_settings()
    try:
        client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.delete(_email_key(email))
        finally:
            await client.aclose()
    except Exception:
        return


__all__ = [
    "ThrottleVerdict",
    "check",
    "record_failure",
    "reset_email",
    "IP_MAX_FAILURES",
    "EMAIL_MAX_FAILURES",
    "IP_WINDOW_SECONDS",
    "EMAIL_WINDOW_SECONDS",
]
