"""Unit tests for built-in Custom CMS page types (app.cms.custom_page_types).

The 'match' page type posts to /add-sport-page on Create and /update-sport-page
on Update (the operation selects the endpoint; there's no ``action`` body field
and no upsert). A create keeps the sport fields present even when blank (the
upstream wants ``content: ""`` for a data-only page); an update patches only the
mapped fields and carries ``id``.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.cms.custom import CustomCmsClient, _substitute
from app.cms.custom_page_types import (
    CUSTOM_PAGE_TYPES,
    is_valid_page_type,
    merged_custom_config,
    supported_operations,
)

_SPORT_KEYS = {
    "lang", "slug", "title", "seo_description", "date", "time",
    "venue", "group", "odds_home", "odds_draw", "odds_away", "content",
}


# ---- the page-type registry -------------------------------------------------


def test_page_types_are_ordinary_and_match():
    assert CUSTOM_PAGE_TYPES == ("ordinary", "match")
    assert is_valid_page_type("match")
    assert is_valid_page_type(None)
    assert not is_valid_page_type("sport")


def test_match_supports_create_and_update_only():
    assert supported_operations("match") == ("create", "update")
    assert supported_operations("ordinary") is None  # all ops, validated per-cms


def test_ordinary_returns_domain_config_unchanged():
    dom = {"endpoint_path": "/api/posts", "body_template": {"t": "{{t}}"}}
    assert merged_custom_config(dom, "ordinary") is dom
    assert merged_custom_config(dom, None) is dom


def test_match_create_uses_add_endpoint_keeps_response_paths():
    dom = {
        "endpoint_path": "/api/posts",
        "body_template": {"title": "{{title}}"},
        "response_id_path": "data.id",
        "response_url_path": "data.url",
    }
    cfg = merged_custom_config(dom, "match", operation="create")
    assert cfg["endpoint_path"] == "/add-sport-page"
    assert cfg["response_id_path"] == "data.id"  # domain's response paths kept
    # body = id + sport fields + the boolean 'top', NO action.
    assert set(cfg["body_template"].keys()) == _SPORT_KEYS | {"id", "top"}
    assert "action" not in cfg["body_template"]
    # create keeps blank sport fields; 'top' is a boolean field (not kept-empty)
    assert set(cfg["send_empty_fields"]) == _SPORT_KEYS
    assert cfg["boolean_fields"] == ["top"]


def test_match_update_uses_update_endpoint_and_drops_blanks():
    cfg = merged_custom_config(None, "match", operation="update")
    assert cfg["endpoint_path"] == "/update-sport-page"
    # update patches → no keep-empty list
    assert "send_empty_fields" not in cfg


# ---- keep_empty_keys behavior in _substitute --------------------------------


def test_keep_empty_keys_pins_a_blank_key_but_drops_id():
    body = {"id": "{{id}}", "content": "{{content}}", "title": "{{title}}"}
    out = _substitute(
        body, {"content": "", "title": "Final"}, keep_empty_keys=frozenset({"content"})
    )
    assert out == {"content": "", "title": "Final"}  # id dropped, content kept


# ---- publish_post end-to-end body shape -------------------------------------


def _run_match_publish(fields: dict, operation: str, captured: dict):
    cfg = merged_custom_config(
        {"endpoint_path": "/api/posts", "body_template": {"title": "{{title}}"},
         "response_id_path": "id", "response_url_path": "url"},
        "match",
        operation=operation,
    )
    client = CustomCmsClient(
        base_url="https://example.com",
        credentials="login:password",
        auth_type="basic_auth",
        custom_config=cfg,
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {"id": "p1", "url": "/en/x/"}

    async def _fake_post(url, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        return mock_resp

    with patch("app.cms.custom.httpx.AsyncClient") as mac:
        mac.return_value.__aenter__.return_value.post = AsyncMock(side_effect=_fake_post)
        return asyncio.run(client.publish_post(fields=fields, language="en"))


def test_match_create_posts_to_add_endpoint_all_keys_no_action_no_id():
    captured: dict = {}
    result = _run_match_publish(
        {
            "slug": "mexico-vs-korea", "title": "Mexico vs Korea", "seo_description": "x",
            "date": "June 19", "time": "01:00", "venue": "Akron",
            "odds_home": "2.02", "odds_draw": "3.25", "odds_away": "4.00", "content": "",
        },
        "create",
        captured,
    )
    assert result.ok is True
    assert captured["url"] == "https://example.com/add-sport-page"
    body = captured["json"]
    assert "action" not in body
    assert "id" not in body            # empty id dropped on create
    assert body["content"] == ""       # kept on create
    assert body["group"] == ""         # unmapped sport field kept on create
    assert set(body) == _SPORT_KEYS


def test_match_update_posts_to_update_endpoint_with_id_drops_blanks():
    captured: dict = {}
    result = _run_match_publish(
        {
            "id": "page_42",
            "odds_home": "1.90", "odds_draw": "3.40", "odds_away": "4.20",
            "slug": "", "title": "", "content": "",  # blank → must not be sent
        },
        "update",
        captured,
    )
    assert result.ok is True
    assert captured["url"] == "https://example.com/update-sport-page"
    body = captured["json"]
    assert "action" not in body
    assert body["id"] == "page_42"
    assert body["odds_home"] == "1.90"
    assert "content" not in body and "title" not in body and "slug" not in body


def test_match_top_field_is_sent_as_json_boolean():
    """The 'top' column holds true/false TEXT but must go out as a real JSON
    boolean (developer requirement)."""
    cases = [
        ("true", True), ("false", False), ("TRUE", True), ("1", True),
        ("0", False), ("yes", True), ("", False), ("no", False),
    ]
    for raw, expected in cases:
        captured: dict = {}
        _run_match_publish({"slug": "x", "top": raw}, "create", captured)
        sent = captured["json"]["top"]
        assert isinstance(sent, bool), f"{raw!r} → {sent!r} is not a bool"
        assert sent is expected, f"{raw!r} → {sent!r}, expected {expected}"


def test_match_top_unmapped_is_not_sent():
    """An unmapped 'top' isn't forced into the body (no stray top:false)."""
    captured: dict = {}
    _run_match_publish({"slug": "x"}, "create", captured)
    assert "top" not in captured["json"]


# ---- request-schema guard: match has no upsert ------------------------------


def test_schema_rejects_match_upsert_allows_create_update():
    import pydantic

    from app.schemas.publish import BulkPublishRequest

    base = dict(table_id=1, mode="single", domain_id=2, custom_page_type="match",
                field_to_column={"slug": 5})
    assert BulkPublishRequest(**base, operation="create").operation == "create"
    assert BulkPublishRequest(
        **base, operation="update", lookup_kind="id", lookup_column_id=6
    ).operation == "update"
    try:
        BulkPublishRequest(**base, operation="upsert")
        raise SystemExit("FAIL: match+upsert should be rejected")
    except pydantic.ValidationError as e:
        assert "upsert" in str(e).lower()
