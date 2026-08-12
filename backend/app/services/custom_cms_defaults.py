"""Shared Custom-CMS connection defaults (Settings → Publishing).

Every Custom CMS site in this workspace talks to the same in-house CMS: same
endpoint, same JSON body shape, same basic-auth credentials. Repeating that per
domain made adding sites a chore and changing the contract impossible without
editing each one, so it lives here once and domains are stamped from it.

Two consumers:
  * the simplified bulk add (``POST /domains/bulk-simple``) — the operator
    pastes ``domain.com - en, es, ru`` lines and every other field comes from
    here;
  * ``reapply_to_domains`` — pushes the current config onto existing Custom
    domains after the CMS contract changes (new field, moved endpoint), which
    is otherwise a per-domain edit.

Shipped defaults mirror ``frontend/public/samples/domains/custom-cms.csv`` so a
fresh install already matches the real CMS. The password is encrypted at rest
and never returned — same handling as the Autotool API key
(services/autotool_config.py).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.db.models import AppSetting, Domain
from app.schemas.domain import (
    CustomCmsDefaultsRead,
    CustomCmsDefaultsUpdate,
    CustomConfig,
)
from app.services.app_settings_cache import invalidate

CONFIG_KEY = "custom_cms_defaults"

# Mirrors the shipped Custom CMS sample CSV — the real contract in use.
DEFAULT_ENDPOINT_PATH = "/index.php?__add_content=1"
DEFAULT_BODY_TEMPLATE: dict[str, Any] = {
    "id": "{{id}}",
    "lang": "{{lang}}",
    "slug": "{{slug}}",
    "title": "{{title}}",
    "action": "{{action}}",
    "content": "{{content}}",
    "seo_title": "{{seo_title}}",
    "seo_description": "{{seo_description}}",
}
DEFAULT_RESPONSE_ID_PATH = "data.id"
DEFAULT_RESPONSE_URL_PATH = "data.url"
# Custom CMS supports bearer / api_key_header / basic_auth; the in-house CMS
# uses basic auth, and the whole point here is one shared credential.
AUTH_TYPE = "basic_auth"


async def _read_raw(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, CONFIG_KEY)
    if row is None:
        return {}
    raw = row.value
    return dict(raw) if isinstance(raw, dict) else {}


def _endpoint(raw: dict[str, Any]) -> str:
    return (raw.get("endpoint_path") or DEFAULT_ENDPOINT_PATH).strip()


def _body_template(raw: dict[str, Any]) -> dict[str, Any]:
    bt = raw.get("body_template")
    return dict(bt) if isinstance(bt, dict) and bt else dict(DEFAULT_BODY_TEMPLATE)


def _public_view(raw: dict[str, Any]) -> CustomCmsDefaultsRead:
    return CustomCmsDefaultsRead(
        endpoint_path=_endpoint(raw),
        body_template=_body_template(raw),
        response_id_path=raw.get("response_id_path") or DEFAULT_RESPONSE_ID_PATH,
        response_url_path=raw.get("response_url_path") or DEFAULT_RESPONSE_URL_PATH,
        credentials_configured=bool(raw.get("credentials_encrypted")),
    )


async def read_defaults(db: AsyncSession) -> CustomCmsDefaultsRead:
    return _public_view(await _read_raw(db))


async def update_defaults(
    db: AsyncSession, payload: CustomCmsDefaultsUpdate, user_id: int | None
) -> CustomCmsDefaultsRead:
    raw = await _read_raw(db)
    data = payload.model_dump(exclude_unset=True)

    # Secret handled separately so it's never stored plaintext.
    # "" → clear, non-empty → replace, None/omitted → unchanged.
    if "credentials" in data:
        cred = data.pop("credentials")
        if cred == "":
            raw.pop("credentials_encrypted", None)
        elif cred:
            raw["credentials_encrypted"] = encrypt(cred)

    for key in (
        "endpoint_path",
        "response_id_path",
        "response_url_path",
    ):
        if key in data:
            val = (data[key] or "").strip()
            if val:
                raw[key] = val
            else:
                raw.pop(key, None)
    if "body_template" in data and data["body_template"] is not None:
        raw["body_template"] = data["body_template"]

    stmt = (
        pg_insert(AppSetting)
        .values(key=CONFIG_KEY, value=raw, updated_by_id=user_id)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": raw, "updated_by_id": user_id},
        )
    )
    await db.execute(stmt)
    await db.commit()
    invalidate(CONFIG_KEY)
    return _public_view(raw)


def build_custom_config(raw: dict[str, Any]) -> CustomConfig:
    """The ``custom_config`` blob to stamp onto a domain."""
    return CustomConfig(
        endpoint_path=_endpoint(raw),
        body_template=_body_template(raw),
        response_id_path=raw.get("response_id_path") or DEFAULT_RESPONSE_ID_PATH,
        response_url_path=raw.get("response_url_path") or DEFAULT_RESPONSE_URL_PATH,
    )


async def effective(db: AsyncSession) -> tuple[CustomConfig, str | None]:
    """``(custom_config, plaintext_credentials)`` for stamping onto domains.

    Credentials are None when unset — the caller decides whether that's fatal
    (a domain without them can't publish) or merely left as-is.
    """
    raw = await _read_raw(db)
    creds: str | None = None
    enc = raw.get("credentials_encrypted")
    if enc:
        try:
            creds = decrypt(enc)
        except Exception:
            creds = None
    return build_custom_config(raw), creds


async def reapply_to_domains(db: AsyncSession, *, include_credentials: bool = True) -> int:
    """Push the current config onto every live Custom CMS domain.

    For when the CMS contract changes for all sites at once. Languages, names
    and per-domain rate limits are untouched — only the connection config (and
    optionally the shared password). Returns how many domains were updated.
    """
    cfg, creds = await effective(db)
    rows = (
        (
            await db.execute(
                select(Domain).where(
                    Domain.cms_type == "custom",
                    Domain.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    blob = cfg.model_dump()
    for d in rows:
        d.custom_config = blob
        d.auth_type = AUTH_TYPE
        if include_credentials and creds:
            d.credentials_encrypted = encrypt(creds)
    await db.commit()
    return len(rows)
