"""Tests for ``default_wp_profiles`` and the seed-on-create policy.

These cover the schema helper directly. The API wiring is exercised by
inspecting the bytes the helper returns — the create path in
``app/api/domains.py`` plugs it in unconditionally for WP rows without a
publish_config, so a focused unit test on the helper + a structural check
catches the regressions we care about (missing fields, broken types, an
accidental switch of post_type from ``posts``/``pages``).
"""
from __future__ import annotations

import pytest

from app.schemas.domain import (
    PublishConfig,
    _has_profiles,
    default_wp_profiles,
    normalize_publish_config,
)


def _by_name(profiles: list[dict]) -> dict[str, dict]:
    return {p["name"]: p for p in profiles}


def test_default_wp_profiles_has_post_and_page():
    cfg = default_wp_profiles()
    assert "profiles" in cfg
    by_name = _by_name(cfg["profiles"])
    assert set(by_name.keys()) == {"Post", "Page"}
    assert by_name["Post"]["post_type"] == "posts"
    assert by_name["Page"]["post_type"] == "pages"


def test_default_post_profile_has_featured_media_as_media_url():
    cfg = default_wp_profiles()
    post = _by_name(cfg["profiles"])["Post"]
    fm = next(f for f in post["fields"] if f["key"] == "featured_media")
    assert fm["type"] == "media_url"


def test_default_page_profile_has_featured_media_as_media_url():
    cfg = default_wp_profiles()
    page = _by_name(cfg["profiles"])["Page"]
    fm = next(f for f in page["fields"] if f["key"] == "featured_media")
    assert fm["type"] == "media_url"


def test_default_post_profile_has_taxonomy_fields():
    cfg = default_wp_profiles()
    post = _by_name(cfg["profiles"])["Post"]
    fields_by_key = {f["key"]: f for f in post["fields"]}
    assert fields_by_key["categories"]["type"] == "taxonomy_ids"
    assert fields_by_key["tags"]["type"] == "taxonomy_ids"


def test_default_profiles_validate_against_pydantic_schema():
    """The seed has to round-trip through PublishConfig — otherwise the
    create endpoint would store something the read endpoint can't return."""
    cfg = default_wp_profiles()
    parsed = PublishConfig.model_validate(cfg)
    assert {p.name for p in parsed.profiles} == {"Post", "Page"}


def test_has_profiles_detects_new_shape():
    assert _has_profiles({"profiles": [{"name": "X", "post_type": "posts"}]}) is True


def test_has_profiles_detects_legacy_shape():
    """A legacy single-config shape should NOT be clobbered by the default-seed."""
    assert _has_profiles({"post_type": "posts", "fields": []}) is True
    assert _has_profiles({"fields": [{"key": "title", "label": "Title"}]}) is True


def test_has_profiles_false_for_empty_and_none():
    assert _has_profiles(None) is False
    assert _has_profiles({}) is False
    assert _has_profiles({"profiles": []}) is False


def test_normalize_does_not_disturb_default_seed():
    """normalize_publish_config should pass the seed through unchanged."""
    cfg = default_wp_profiles()
    assert normalize_publish_config(cfg) is cfg


@pytest.mark.parametrize("profile_name", ["Post", "Page"])
def test_default_profile_has_required_title_and_content(profile_name: str):
    cfg = default_wp_profiles()
    profile = _by_name(cfg["profiles"])[profile_name]
    by_key = {f["key"]: f for f in profile["fields"]}
    assert by_key["title"]["required"] is True
    assert by_key["content"]["required"] is True
