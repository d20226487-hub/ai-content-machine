"""Shared Films connection settings (Settings -> Publishing).

Every Films site runs the same CSV import API (app/cms/films.py) behind the
same basic-auth account — a different one from the Custom CMS fleet. So the
login/password live here once:

  * the simplified bulk add (``POST /domains/bulk-simple`` with
    ``cms_type='films'``) stamps them onto each new domain;
  * saving new credentials here re-stamps them onto every live Films domain.

Re-stamping is automatic (unlike Custom CMS's explicit "apply to all") because
a Films domain carries nothing else to preserve: no languages, no body
template, no per-site endpoint — the credentials ARE its whole config, and the
operator's intent in changing the shared password is exactly "use this
everywhere". Only ``credentials_encrypted`` + ``auth_type`` are touched.

Credentials are stored encrypted as ``login:password`` (the form the client's
basic-auth header expects); the password is never returned.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms.films import ENDPOINT_PATH
from app.core.crypto import decrypt, encrypt
from app.db.models import AppSetting, Domain
from app.schemas.domain import FilmsDefaultsRead, FilmsDefaultsUpdate
from app.services.app_settings_cache import invalidate

CONFIG_KEY = "films_defaults"
AUTH_TYPE = "basic_auth"


async def _read_raw(db: AsyncSession) -> dict[str, Any]:
    row = await db.get(AppSetting, CONFIG_KEY)
    if row is None:
        return {}
    return dict(row.value) if isinstance(row.value, dict) else {}


def _decrypt(raw: dict[str, Any]) -> str | None:
    enc = raw.get("credentials_encrypted")
    if not enc:
        return None
    try:
        return decrypt(enc)
    except Exception:  # noqa: BLE001 — a bad blob reads as "not configured"
        return None


async def _domain_count(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count(Domain.id)).where(
                Domain.cms_type == "films", Domain.deleted_at.is_(None)
            )
        )
    ).scalar_one()


async def read_defaults(db: AsyncSession) -> FilmsDefaultsRead:
    raw = await _read_raw(db)
    creds = _decrypt(raw)
    return FilmsDefaultsRead(
        credentials_configured=bool(creds),
        login=(creds or "").partition(":")[0],
        endpoint_path=ENDPOINT_PATH,
        domain_count=await _domain_count(db),
    )


async def effective_credentials(db: AsyncSession) -> str | None:
    """Plaintext ``login:password`` for stamping onto domains, or None."""
    return _decrypt(await _read_raw(db))


async def update_defaults(
    db: AsyncSession, payload: FilmsDefaultsUpdate, user_id: int | None
) -> FilmsDefaultsRead:
    raw = await _read_raw(db)
    current = _decrypt(raw)
    cur_login, _, cur_password = (current or "").partition(":")
    data = payload.model_dump(exclude_unset=True)

    if data.get("password") == "":
        # Explicit clear. Domains keep what they were stamped with — clearing
        # the shared setting shouldn't silently break publishing fleet-wide.
        raw.pop("credentials_encrypted", None)
        new_creds = None
    else:
        login = (data.get("login") if data.get("login") is not None else cur_login).strip()
        password = data.get("password") if data.get("password") is not None else cur_password
        password = (password or "").strip()
        new_creds = f"{login}:{password}" if (login and password) else None
        if new_creds:
            raw["credentials_encrypted"] = encrypt(new_creds)

    await db.execute(
        pg_insert(AppSetting)
        .values(key=CONFIG_KEY, value=raw, updated_by_id=user_id)
        .on_conflict_do_update(
            index_elements=["key"], set_={"value": raw, "updated_by_id": user_id}
        )
    )

    if new_creds and new_creds != current:
        rows = (
            await db.execute(
                select(Domain).where(
                    Domain.cms_type == "films", Domain.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        for d in rows:
            d.auth_type = AUTH_TYPE
            d.credentials_encrypted = encrypt(new_creds)

    await db.commit()
    invalidate(CONFIG_KEY)
    return await read_defaults(db)
