"""Grounded sources -> sibling column text (fed to Link-Fix).

One "Title — URL" per cited source; sources without a URI are dropped, titles
are optional. The endpoint that builds the column is exercised against the
running stack.
"""
from __future__ import annotations

from app.api.library import _format_grounding_sources


def test_formats_title_and_url_per_line():
    gs = {
        "sources": [
            {"uri": "https://a.example/x", "title": "A"},
            {"uri": "https://b.example/y", "title": ""},  # no title -> URL only
            {"title": "no uri"},  # dropped
            {"uri": "https://c.example/z"},
        ]
    }
    out = _format_grounding_sources(gs)
    assert out == (
        "A — https://a.example/x\n"
        "https://b.example/y\n"
        "https://c.example/z"
    )


def test_empty_inputs_yield_empty_string():
    assert _format_grounding_sources(None) == ""
    assert _format_grounding_sources({}) == ""
    assert _format_grounding_sources({"sources": []}) == ""
