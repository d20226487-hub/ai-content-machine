"""Unit tests for the Custom CMS client's `basic_auth` path and the
{{lang}} placeholder alias.

These are deliberately pure-Python — no HTTP, no DB — because what we want
to lock in is wire-format behavior:

  - Basic auth header matches the canonical RFC 7617 encoding so any
    reverse proxy in front of the upstream (Cloudflare, nginx) sees the
    expected scheme + base64 token.
  - {{lang}} is interchangeable with {{language}} in body_template so the
    mrba-CRM body shape (``{"lang": "en", ...}``) works without forcing
    users to write {{language}} and have their API drop the value.
"""
from __future__ import annotations

import base64

from app.cms.custom import CustomCmsClient, _substitute


def _client(auth_type: str, credentials: str | None) -> CustomCmsClient:
    return CustomCmsClient(
        base_url="https://example.com",
        credentials=credentials,
        auth_type=auth_type,
        custom_config={},
    )


def test_basic_auth_header_is_rfc7617():
    c = _client("basic_auth", "alice:s3cret")
    h = c._auth_header()
    expected = base64.b64encode(b"alice:s3cret").decode("ascii")
    assert h == {"Authorization": f"Basic {expected}"}


def test_basic_auth_header_unicode_password():
    """Non-ASCII passwords must be UTF-8 encoded before base64."""
    c = _client("basic_auth", "alice:пароль")
    h = c._auth_header()
    expected = base64.b64encode("alice:пароль".encode("utf-8")).decode("ascii")
    assert h == {"Authorization": f"Basic {expected}"}


def test_basic_auth_with_no_credentials_is_empty():
    """Empty creds = no header. Lets the user point at a public endpoint
    that doesn't actually want auth without our client injecting garbage."""
    c = _client("basic_auth", None)
    assert c._auth_header() == {}


def test_bearer_auth_unaffected():
    """Regression guard: the new branch must not steal the bearer path."""
    c = _client("bearer", "tok123")
    assert c._auth_header() == {"Authorization": "Bearer tok123"}


def test_lang_alias_substitution():
    """When `language` is passed, both {{language}} and {{lang}} resolve
    to the same string — so a body_template using either key works."""
    body = {"lang": "{{lang}}", "language_long": "{{language}}", "slug": "{{slug}}"}
    values = {"language": "en", "lang": "en", "slug": "home"}
    result = _substitute(body, values)
    assert result == {"lang": "en", "language_long": "en", "slug": "home"}


def test_explicit_lang_field_overrides_alias():
    """If the caller passed an explicit `lang` key in fields, it wins
    over the language-derived alias — setdefault is one-shot."""
    body = {"lang": "{{lang}}"}
    # Simulating what publish_post does: values starts from fields, then
    # setdefault adds language/lang only if absent.
    values = {"lang": "ru"}
    values.setdefault("language", "en")
    values.setdefault("lang", "en")
    assert _substitute(body, values) == {"lang": "ru"}


# ---- drop-empty behavior ----------------------------------------------------
#
# These pin the invariant that lets one body_template cover create / update /
# upsert: when a bare {{key}} placeholder resolves to missing-or-empty, the
# whole key/value pair is dropped from the outgoing body. Previously the
# literal string ``"{{id}}"`` would have been sent.


def test_missing_placeholder_drops_key_from_dict():
    body = {"id": "{{id}}", "title": "{{title}}"}
    assert _substitute(body, {"title": "hello"}) == {"title": "hello"}


def test_empty_string_placeholder_drops_key():
    """An empty input field is the same as 'didn't provide it'."""
    body = {"id": "{{id}}", "title": "{{title}}"}
    assert _substitute(body, {"id": "", "title": "hello"}) == {"title": "hello"}


def test_none_placeholder_drops_key():
    body = {"id": "{{id}}", "title": "{{title}}"}
    assert _substitute(body, {"id": None, "title": "hello"}) == {"title": "hello"}


def test_all_keys_dropped_yields_empty_dict():
    body = {"id": "{{id}}", "slug": "{{slug}}"}
    assert _substitute(body, {}) == {}


def test_create_action_payload_shape():
    """Create: action+lang+slug+content present, id blank → dropped."""
    body = {
        "action": "{{action}}",
        "id": "{{id}}",
        "lang": "{{lang}}",
        "slug": "{{slug}}",
        "title": "{{title}}",
        "content": "{{content}}",
    }
    values = {
        "action": "create",
        "id": "",
        "lang": "en",
        "slug": "new-page",
        "title": "Hi",
        "content": "<p>Hi</p>",
    }
    assert _substitute(body, values) == {
        "action": "create",
        "lang": "en",
        "slug": "new-page",
        "title": "Hi",
        "content": "<p>Hi</p>",
    }


def test_update_action_payload_shape():
    """Update: only action+id+fields-being-changed survive; lang/slug dropped."""
    body = {
        "action": "{{action}}",
        "id": "{{id}}",
        "lang": "{{lang}}",
        "slug": "{{slug}}",
        "title": "{{title}}",
        "seo_description": "{{seo_description}}",
    }
    values = {
        "action": "update",
        "id": "page_abc",
        "lang": "",
        "slug": "",
        "title": "New title",
        "seo_description": "New meta",
    }
    assert _substitute(body, values) == {
        "action": "update",
        "id": "page_abc",
        "title": "New title",
        "seo_description": "New meta",
    }


def test_interpolation_still_substitutes_empty_for_missing():
    """Regression guard: only PURE {{key}} placeholders get dropped.
    Interpolated strings keep their empty-string fallback so we don't
    accidentally break callers that depend on that path."""
    body = {"url": "/posts/{{slug}}"}
    assert _substitute(body, {}) == {"url": "/posts/"}


def test_list_drops_missing_entries():
    body = {"tags": ["{{tag_a}}", "{{tag_b}}", "{{tag_c}}"]}
    assert _substitute(body, {"tag_b": "kept"}) == {"tags": ["kept"]}


# ---- relative-URL absolutization --------------------------------------------
#
# The publish history renders cms_post_url as a clickable anchor. Some CMSes
# return relative paths in their response — those would resolve against ACM's
# own origin, not the target site. Pin the absolutization here.


def test_relative_url_is_absolutized_against_base_url():
    """Mock the HTTP round-trip and assert the post-processing path."""
    import asyncio
    from unittest.mock import patch, MagicMock, AsyncMock

    from app.cms.custom import CustomCmsClient

    cfg = {
        "endpoint_path": "/index.php?__add_content=1",
        "body_template": {"slug": "{{slug}}", "content": "{{content}}"},
        "response_id_path": "data.id",
        "response_url_path": "data.url",
    }
    client = CustomCmsClient(
        base_url="https://test-crm.mrba-stage1.xyz",
        credentials="login:password",
        auth_type="basic_auth",
        custom_config=cfg,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "ok": True,
        "data": {"id": "page_abc", "url": "/en/test-page/"},
    }

    async def _fake_post(*a, **kw):
        return mock_resp

    with patch("app.cms.custom.httpx.AsyncClient") as mac:
        mac.return_value.__aenter__.return_value.post = AsyncMock(side_effect=_fake_post)
        result = asyncio.run(
            client.publish_post(
                fields={"slug": "test-page", "content": "<p>x</p>"},
                language="en",
            )
        )

    assert result.ok is True
    assert result.cms_post_id == "page_abc"
    # Was "/en/test-page/", now absolute.
    assert result.cms_post_url == "https://test-crm.mrba-stage1.xyz/en/test-page/"


def test_absolute_url_passes_through_unchanged():
    """Pre-absolute response URLs are not double-prefixed."""
    import asyncio
    from unittest.mock import patch, MagicMock, AsyncMock

    from app.cms.custom import CustomCmsClient

    client = CustomCmsClient(
        base_url="https://test-crm.mrba-stage1.xyz",
        credentials="login:password",
        auth_type="basic_auth",
        custom_config={
            "endpoint_path": "/x",
            "body_template": {},
            "response_id_path": "id",
            "response_url_path": "url",
        },
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {"id": "p1", "url": "https://other-host.example/p1"}

    async def _fake_post(*a, **kw):
        return mock_resp

    with patch("app.cms.custom.httpx.AsyncClient") as mac:
        mac.return_value.__aenter__.return_value.post = AsyncMock(side_effect=_fake_post)
        result = asyncio.run(client.publish_post(fields={}, language="en"))

    assert result.cms_post_url == "https://other-host.example/p1"
