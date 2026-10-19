"""Vertex locations: the global endpoint, and Claude's own location.

A Vertex project isn't tied to a region — every request names its location in
the URL. Two things follow:
  * ``location="global"`` must hit ``aiplatform.googleapis.com`` (there is no
    ``global-aiplatform.googleapis.com``);
  * Claude isn't offered in every region Gemini is (europe-west3 is Gemini
    only), so Claude can use its own ``claude_location`` while Gemini stays
    where it is. Empty falls back to the shared ``location``.
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import patch

import pytest

from app.providers.base import GenerationParams
from app.providers.vertex_ai import VertexAIProvider, vertex_host


@pytest.mark.parametrize("loc,host", [
    ("global", "aiplatform.googleapis.com"),
    (" GLOBAL ", "aiplatform.googleapis.com"),
    ("europe-west3", "europe-west3-aiplatform.googleapis.com"),
    ("us-central1", "us-central1-aiplatform.googleapis.com"),
])
def test_vertex_host(loc, host):
    assert vertex_host(loc) == host


def _provider(**extra):
    return VertexAIProvider(
        api_key="",
        default_model="gemini-3-flash",
        extra_config={"service_account_json": "{}", "project_id": "proj", **extra},
    )


def _gemini_url(location: str) -> str:
    p = _provider(location=location)
    with patch("app.providers.vertex_ai._mint_vertex_access_token", return_value="tok"):
        url, _headers, _params = p._sa_target("{}", "gemini-3-flash")
    return url


def test_gemini_global_url():
    assert _gemini_url("global") == (
        "https://aiplatform.googleapis.com/v1/projects/proj/locations/global/"
        "publishers/google/models/gemini-3-flash:generateContent"
    )


def test_gemini_regional_url_unchanged():
    assert _gemini_url("europe-west3").startswith(
        "https://europe-west3-aiplatform.googleapis.com/v1/projects/proj/locations/europe-west3/"
    )


def test_gemini_ignores_claude_location():
    p = _provider(location="europe-west3", claude_location="global")
    with patch("app.providers.vertex_ai._mint_vertex_access_token", return_value="tok"):
        url, _, _ = p._sa_target("{}", "gemini-3-flash")
    assert "europe-west3-aiplatform.googleapis.com" in url


def _claude_region(**extra) -> str:
    """Run a Claude generation with the Anthropic SDK stubbed; return the
    region the client was built with."""
    seen: dict[str, str] = {}

    class _Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get_final_message(self):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="ok")],
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1),
                stop_reason="end_turn",
            )

    class FakeClient:
        def __init__(self, *, project_id, region, credentials, max_retries):
            seen["region"] = region
            self.messages = types.SimpleNamespace(stream=lambda **kw: _Stream())

        async def close(self):
            pass

    fake_anthropic = types.ModuleType("anthropic")
    fake_anthropic.AsyncAnthropicVertex = FakeClient
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), patch(
        "app.providers.vertex_ai._vertex_credentials", return_value=object()
    ):
        asyncio.run(
            _provider(**extra).generate(
                prompt="hi", model="claude-sonnet-5", params=GenerationParams()
            )
        )
    return seen["region"]


def test_claude_uses_its_own_location():
    assert _claude_region(location="europe-west3", claude_location="global") == "global"


def test_claude_falls_back_to_the_shared_location():
    assert _claude_region(location="us-east5") == "us-east5"
