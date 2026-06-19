"""Built-in Custom CMS "page types" for bulk publish.

A bulk-publish run against a Custom CMS domain can target one of several
*page types*. A non-default page type pins a fixed endpoint + body template
that OVERRIDES whatever the domain itself is configured with — so one domain
can serve more than one kind of page without a second Domain row or a full
profiles system.

  * ``ordinary`` — the default. No override; the run uses the domain's own
    ``endpoint_path`` + ``body_template`` (today's behavior, unchanged).
  * ``match`` — sport "match" pages, with the match field set (date / time /
    venue / group / odds_* …). The OPERATION picks the endpoint: Create posts
    to ``/add-sport-page``, Update posts to ``/update-sport-page`` (the post is
    addressed by ``id``). Only create + update are supported (no upsert). The
    domain's own endpoint + body_template are ignored; auth and the
    response-id/url paths still come from the domain.

The field keys a page type exposes are exactly its body_template
placeholders. The frontend mirrors the same list (``MATCH_PAGE_FIELDS`` in
``lib/publishBulk.ts``) so the bulk field-mapping panel shows the right slots
regardless of which domain a row resolves to — which is also why ``match``
sidesteps the "multi mode reads one canonical domain's template" limitation:
the schema is a constant, not a per-domain read.

``lang`` is intentionally part of the template but is fed by the run's
language picker / language column (the client fills ``{{lang}}`` from the
resolved language), so it is NOT offered as a mappable field slot.
"""
from __future__ import annotations

from typing import Any

ORDINARY = "ordinary"
MATCH = "match"

# Every valid value for the run / request `custom_page_type` field.
CUSTOM_PAGE_TYPES: tuple[str, ...] = (ORDINARY, MATCH)

# Sport fields that must stay in the body even when blank on a CREATE (the
# reference curl sends ``content: ""`` for a data-only page). ``id`` is NOT
# here on purpose: it's dropped on create / supplied on update.
_MATCH_KEEP_EMPTY: tuple[str, ...] = (
    "lang", "slug", "title", "seo_title", "seo_description", "date", "time",
    "venue", "group", "odds_home", "odds_draw", "odds_away", "content",
)

# Fields the upstream expects as a JSON boolean, not a string — their table
# cell holds "true"/"false" text, which CustomCmsClient.publish_post coerces
# to a real bool before sending. Deliberately NOT in _MATCH_KEEP_EMPTY: a
# mapped-but-blank cell becomes ``false`` (handled by the coercion), and an
# unmapped one is dropped rather than sent as the string "".
_MATCH_BOOLEAN: tuple[str, ...] = ("top",)

# The match body template. There's no ``action`` field — the operation picks
# the endpoint instead. ``id`` is a bare placeholder → dropped when blank
# (create), present when supplied (update, to address the existing page).
_MATCH_BODY_TEMPLATE: dict[str, Any] = {
    "id": "{{id}}",
    **{k: f"{{{{{k}}}}}" for k in _MATCH_KEEP_EMPTY},
    **{k: f"{{{{{k}}}}}" for k in _MATCH_BOOLEAN},
}

# Per-operation endpoint for the match page type (the operation, not an
# ``action`` body field, selects the URL).
_MATCH_ENDPOINTS: dict[str, str] = {
    "create": "/add-sport-page",
    "update": "/update-sport-page",
}

# Endpoint + body_template + per-operation rules per non-default page type.
# ``ordinary`` is absent on purpose — it means "use the domain's own config".
_OVERRIDES: dict[str, dict[str, Any]] = {
    MATCH: {
        "endpoints": _MATCH_ENDPOINTS,
        "operations": ("create", "update"),  # no upsert for match
        "body_template": _MATCH_BODY_TEMPLATE,
        "keep_empty": _MATCH_KEEP_EMPTY,
        "boolean_fields": _MATCH_BOOLEAN,
    },
}


def is_valid_page_type(value: str | None) -> bool:
    return (value or ORDINARY) in CUSTOM_PAGE_TYPES


def supported_operations(page_type: str | None) -> tuple[str, ...] | None:
    """Operations a page type allows, or None for ``ordinary`` (all of
    create/update/upsert, validated elsewhere per cms_type)."""
    spec = _OVERRIDES.get(page_type or ORDINARY)
    return spec["operations"] if spec else None


def merged_custom_config(
    domain_custom_config: dict | None,
    page_type: str | None,
    operation: str = "create",
) -> dict | None:
    """Domain custom_config with the page-type endpoint/template applied.

    Keeps the domain's auth-irrelevant fields (response_id_path,
    response_url_path, homepage_slug, …) and only swaps ``endpoint_path`` +
    ``body_template``. Returns the domain config unchanged for ``ordinary``
    (or any unknown type), so the default publish path is untouched.

    ``operation`` selects BOTH the endpoint (create → /add-sport-page,
    update → /update-sport-page) and the blank-field policy: a create keeps
    the full sport set so a new page carries ``content: ""``
    (``send_empty_fields``); an update patches only the mapped fields
    (default drop-empty). Unknown operations fall back to the create endpoint.
    """
    spec = _OVERRIDES.get(page_type or ORDINARY)
    if spec is None:
        return domain_custom_config
    endpoints = spec["endpoints"]
    merged = {
        **(domain_custom_config or {}),
        "endpoint_path": endpoints.get(operation, endpoints["create"]),
        "body_template": spec["body_template"],
    }
    if operation == "create":
        merged["send_empty_fields"] = list(spec["keep_empty"])
    # Boolean coercion applies to both create and update (you can flip the
    # flag on an update too); publish_post converts the mapped text cell.
    if spec.get("boolean_fields"):
        merged["boolean_fields"] = list(spec["boolean_fields"])
    return merged
