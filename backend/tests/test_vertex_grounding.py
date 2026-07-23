"""Grounding on the Vertex Gemini path.

Two things matter: the request must carry the Google Search tool ONLY when the
column asked for grounding, and the reply's ``groundingMetadata`` must be
distilled into the compact ``{queries, sources}`` we store on the cell. The
HTTP call is mocked so the test needs no Vertex project.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.providers.base import GenerationParams
from app.providers.vertex_ai import VertexAIProvider, _parse_grounding


# ---- pure parser ------------------------------------------------------------


def test_parse_grounding_extracts_queries_and_sources():
    cand = {
        "groundingMetadata": {
            "webSearchQueries": ["best espresso 2026", ""],
            "groundingChunks": [
                {"web": {"uri": "https://a.example/x", "title": "A"}},
                {"web": {"uri": "https://b.example/y"}},  # missing title
                {"web": {"title": "no uri"}},             # dropped (no uri)
                {"retrievedContext": {}},                 # non-web chunk, ignored
            ],
            "searchEntryPoint": {"renderedContent": "<div/>"},  # dropped
        }
    }
    out = _parse_grounding(cand)
    assert out == {
        "queries": ["best espresso 2026"],
        "sources": [
            {"uri": "https://a.example/x", "title": "A"},
            {"uri": "https://b.example/y", "title": ""},
        ],
    }


@pytest.mark.parametrize(
    "cand",
    [
        {"content": {"parts": []}},          # no metadata at all
        {"groundingMetadata": {}},           # empty metadata
        {"groundingMetadata": {"groundingChunks": [], "webSearchQueries": []}},
    ],
)
def test_parse_grounding_none_when_absent(cand):
    assert _parse_grounding(cand) is None


# ---- request/response wiring (mocked HTTP) ----------------------------------


class _FakeResp:
    status_code = 200
    text = ""
    headers: dict = {}

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeClient:
    """Captures the last request body and returns a canned response."""

    last_body: dict | None = None
    response: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, params=None, headers=None, json=None):
        _FakeClient.last_body = json
        return _FakeResp(_FakeClient.response)


_GROUNDED_RESPONSE = {
    "candidates": [
        {
            "content": {"parts": [{"text": "Coffee facts…"}]},
            "finishReason": "STOP",
            "groundingMetadata": {
                "webSearchQueries": ["coffee facts 2026"],
                "groundingChunks": [
                    {"web": {"uri": "https://src.example/1", "title": "Src 1"}}
                ],
            },
        }
    ],
    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 34},
}


@pytest.mark.asyncio
async def test_grounded_call_sends_tool_and_parses_sources():
    _FakeClient.response = _GROUNDED_RESPONSE
    provider = VertexAIProvider(api_key="k", default_model="gemini-3-flash")
    with patch("app.providers.vertex_ai.httpx.AsyncClient", _FakeClient):
        result = await provider.generate(
            "research coffee", params=GenerationParams(grounding="google_search")
        )
    # The Google Search tool was attached.
    assert _FakeClient.last_body["tools"] == [{"googleSearch": {}}]
    # And the citations came back distilled onto the result.
    assert result.grounding == {
        "queries": ["coffee facts 2026"],
        "sources": [{"uri": "https://src.example/1", "title": "Src 1"}],
    }
    assert result.text == "Coffee facts…"


@pytest.mark.asyncio
async def test_ungrounded_call_omits_tool_and_has_no_grounding():
    _FakeClient.response = {
        "candidates": [
            {
                "content": {"parts": [{"text": "plain"}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {},
    }
    provider = VertexAIProvider(api_key="k", default_model="gemini-3-flash")
    with patch("app.providers.vertex_ai.httpx.AsyncClient", _FakeClient):
        result = await provider.generate("hi", params=GenerationParams())
    assert "tools" not in _FakeClient.last_body
    assert result.grounding is None
