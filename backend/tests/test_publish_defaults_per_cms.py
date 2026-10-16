"""Publish rate limits are resolved per CMS type.

WordPress REST, the in-house Custom CMS and a Films CSV import tolerate very
different pressure, so each type carries its own defaults. Precedence:
per-domain column → per-CMS setting → legacy single setting → shipped value.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services import publish_rate_limit as prl


def _resolve(settings: dict[str, object], domain) -> prl.DomainRateLimits:
    async def fake_get_settings_many(_db, keys):
        return {k: settings.get(k) for k in keys}

    with patch.object(prl, "get_settings_many", fake_get_settings_many):
        return asyncio.run(prl.resolve_for_domain(None, domain))


def _domain(cms_type: str, **overrides):
    base = dict(
        cms_type=cms_type, requests_per_minute=None, max_concurrency=None,
        inter_request_delay_ms=None, retry_max_attempts=None, backoff_base_ms=None,
        backoff_jitter_ms=None, respect_retry_after=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_per_cms_value_wins_over_the_legacy_default():
    settings = {
        "publish_default_max_concurrency": 8,
        "publish_default_films_max_concurrency": 1,
    }
    assert _resolve(settings, _domain("films")).max_concurrency == 1
    # Other CMS types keep the legacy default — saving one tab can't move another.
    assert _resolve(settings, _domain("custom")).max_concurrency == 8
    assert _resolve(settings, _domain("wordpress")).max_concurrency == 8


def test_legacy_default_applies_when_no_per_cms_value():
    settings = {"publish_default_requests_per_minute": 42}
    for cms in ("wordpress", "custom", "films"):
        assert _resolve(settings, _domain(cms)).requests_per_minute == 42


def test_films_ship_with_one_request_at_a_time():
    # Nothing saved at all: Films default to a single in-flight request (their
    # import handles one CSV at a time); the others keep the shared default.
    assert _resolve({}, _domain("films")).max_concurrency == 1
    assert _resolve({}, _domain("custom")).max_concurrency == prl._HARDCODED.max_concurrency


def test_a_saved_legacy_value_is_not_overridden_by_our_films_opinion():
    # The operator already set 3 globally — we don't silently drop Films to 1.
    settings = {"publish_default_max_concurrency": 3}
    assert _resolve(settings, _domain("films")).max_concurrency == 3


def test_domain_override_still_wins():
    settings = {"publish_default_films_max_concurrency": 1}
    domain = _domain("films", max_concurrency=5)
    assert _resolve(settings, domain).max_concurrency == 5


def test_unknown_cms_type_falls_back_to_the_legacy_default():
    settings = {"publish_default_max_concurrency": 7}
    assert _resolve(settings, _domain("something-else")).max_concurrency == 7
