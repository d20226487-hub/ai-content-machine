"""The publish-job curl preview must show the URL that was ACTUALLY hit.

For Custom CMS built-in page types ('match'), the worker hardcodes the
endpoint (Create → /add-sport-page, Update → /update-sport-page) regardless of
the domain's configured endpoint_path. The preview takes an ``endpoint_override``
so it mirrors that, instead of misleadingly reconstructing the domain's own
endpoint (the bug: a match update showed the domain's /index.php?__add_language=1).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.api.publish import _build_curl_preview


def _job():
    return SimpleNamespace(payload_sent={"id": "p1", "lang": "fr", "title": "x"})


def _domain():
    return SimpleNamespace(
        base_url="https://test-teams.example",
        cms_type="custom",
        custom_config={"endpoint_path": "/index.php?__add_language=1"},
        auth_type="basic_auth",
    )


def test_without_override_uses_domain_endpoint():
    cp = _build_curl_preview(_job(), _domain())
    assert "/index.php?__add_language=1" in cp


def test_match_override_wins_over_domain_endpoint():
    cp = _build_curl_preview(_job(), _domain(), endpoint_override="/update-sport-page")
    assert "https://test-teams.example/update-sport-page" in cp
    assert "__add_language" not in cp


def test_create_override_shows_add_sport_page():
    cp = _build_curl_preview(_job(), _domain(), endpoint_override="/add-sport-page")
    assert "https://test-teams.example/add-sport-page" in cp


def test_body_is_unchanged_by_override():
    """Only the URL is overridden — the body is still the real payload_sent."""
    cp = _build_curl_preview(_job(), _domain(), endpoint_override="/update-sport-page")
    assert '"id": "p1"' in cp and '"title": "x"' in cp
