"""Grounding blacklist normalization — bare hosts, deduped, capped."""
from __future__ import annotations

from app.services.grounding_domains import (
    MAX_EXCLUDE_DOMAINS,
    normalize_exclude_domains,
)


def test_bare_domain_passthrough():
    assert normalize_exclude_domains(["spam.com"]) == ["spam.com"]


def test_strips_scheme_path_www_and_lowercases():
    assert normalize_exclude_domains(["https://WWW.Spam.com/some/path?q=1"]) == [
        "spam.com"
    ]


def test_strips_port_and_userinfo():
    assert normalize_exclude_domains(["user@bad.example.com:8443"]) == [
        "bad.example.com"
    ]


def test_dedupes_case_and_www_variants():
    assert normalize_exclude_domains(
        ["spam.com", "www.spam.com", "SPAM.com"]
    ) == ["spam.com"]


def test_free_text_blob_split():
    assert normalize_exclude_domains("a.com, b.com\n c.com") == [
        "a.com",
        "b.com",
        "c.com",
    ]


def test_drops_invalid_tokens():
    assert normalize_exclude_domains(["", "not a domain", "no-dot", "ok.io"]) == [
        "ok.io"
    ]


def test_none_and_empty():
    assert normalize_exclude_domains(None) == []
    assert normalize_exclude_domains([]) == []
    assert normalize_exclude_domains("") == []


def test_caps_length():
    many = [f"d{i}.com" for i in range(MAX_EXCLUDE_DOMAINS + 10)]
    out = normalize_exclude_domains(many)
    assert len(out) == MAX_EXCLUDE_DOMAINS
    assert out[0] == "d0.com"
