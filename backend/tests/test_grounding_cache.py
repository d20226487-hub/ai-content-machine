"""Grounding memo cache key — stable, sensitive to each field, collision-safe.

The put/get roundtrip, TTL, surcharge event, and preview count are DB-backed and
exercised against the running stack.
"""
from __future__ import annotations

from app.services.grounding_cache import cache_key


def test_key_is_stable_and_64_hex():
    k1 = cache_key("write about cats", "gemini-2.5-pro", "google_search")
    k2 = cache_key("write about cats", "gemini-2.5-pro", "google_search")
    assert k1 == k2
    assert len(k1) == 64 and all(c in "0123456789abcdef" for c in k1)


def test_any_field_change_changes_the_key():
    base = cache_key("write about cats", "gemini-2.5-pro", "google_search")
    assert cache_key("write about dogs", "gemini-2.5-pro", "google_search") != base
    assert cache_key("write about cats", "gemini-2.5-flash", "google_search") != base
    assert cache_key("write about cats", "gemini-2.5-pro", "vertex_ai_search") != base


def test_nul_separator_blocks_field_boundary_collision():
    # Without the NUL separators, ("a","bc") and ("ab","c") would hash the same.
    assert cache_key("a", "bc", "google_search") != cache_key(
        "ab", "c", "google_search"
    )
