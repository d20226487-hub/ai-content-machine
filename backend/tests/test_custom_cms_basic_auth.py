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
