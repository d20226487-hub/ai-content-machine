"""Sync a set of languages to one Custom CMS site via its language endpoint.

The site exposes ``POST /index.php?__add_language=1`` and accepts a body
``{"action": "upsert", "languages": [...]}``. This module wraps that single
call with: stored-credential decryption, SSRF revalidation of the URL we're
about to hit, a short timeout, and a uniform result shape so the parallel
fan-out in the API layer doesn't need to know the details.

We deliberately reuse ``CustomCmsClient._auth_header()`` — the auth scheme
matrix (basic / bearer / api_key_header) already lives there and forking
it here would create two places to update if a new scheme is added.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.cms.custom import CustomCmsClient
from app.core.crypto import decrypt
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url
from app.db.models import Domain
from app.schemas.language_sync import LanguageSyncOneResult


# Path is hardcoded — confirmed identical across the user's Custom CMS
# fleet. If a site ever needs a different path, lift this to a per-domain
# `language_endpoint_path` field on custom_config.
LANGUAGE_ENDPOINT_PATH = "/index.php?__add_language=1"

_TIMEOUT_SECONDS = 15.0


async def sync_one_domain(
    domain: Domain, languages: list[str]
) -> LanguageSyncOneResult:
    """Push a language set to one domain. Never raises — every failure
    mode becomes a populated ``LanguageSyncOneResult`` so the parallel
    fan-out below can ``asyncio.gather`` without per-task exception
    handling.

    Skip conditions (returned with ``skipped=True``):
      * Domain isn't Custom CMS (the language API is custom-CMS-specific).
      * Domain has no stored credentials (we can't authenticate).
    """
    if domain.cms_type != "custom":
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            skipped=True,
            skip_reason=f"Domain is {domain.cms_type}, not Custom CMS",
        )
    if not domain.credentials_encrypted:
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            skipped=True,
            skip_reason="Domain has no credentials configured",
        )

    # Decrypt + build the auth header via the existing client so basic /
    # bearer / api_key_header all just work without re-implementing.
    try:
        creds = decrypt(domain.credentials_encrypted)
    except Exception as e:  # noqa: BLE001 — surface FERNET rotation issues cleanly
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            detail=f"Failed to decrypt credentials: {e}",
        )

    client = CustomCmsClient(
        base_url=domain.base_url,
        credentials=creds,
        auth_type=domain.auth_type,
        custom_config=domain.custom_config or {},
    )
    headers = {**client._auth_header(), "Content-Type": "application/json"}

    # Dedupe + lowercase + strip so callers can pass column values
    # directly without pre-cleaning ("RU", " ru ", "ru" all collapse to "ru").
    normalized = sorted({s.strip().lower() for s in languages if s and s.strip()})
    if not normalized:
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            detail="No valid languages supplied after normalization",
        )

    url = f"{domain.base_url.rstrip('/')}{LANGUAGE_ENDPOINT_PATH}"

    start = time.perf_counter()
    try:
        # SSRF revalidation — defense in depth. base_url was checked at
        # domain create / update, but checking the exact URL we're about
        # to call is cheap and survives misconfigured stored values.
        validate_public_url(url)
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS,
            follow_redirects=True,
            transport=SafeAsyncTransport(),
        ) as http:
            resp = await http.post(
                url,
                headers=headers,
                json={"action": "upsert", "languages": normalized},
            )
        elapsed = int((time.perf_counter() - start) * 1000)
    except UnsafeUrlError as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            detail=f"URL rejected: {e}",
            elapsed_ms=elapsed,
        )
    except httpx.HTTPError as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=False,
            detail=f"Network error: {e}",
            elapsed_ms=elapsed,
        )

    # Success is defined by the API contract — JSON body with `ok: true` —
    # NOT by HTTP status alone. A site without the `__add_language=1`
    # endpoint installed will happily 200 with the rendered homepage HTML,
    # which used to slip through as "ok" and dump a wall of HTML in the
    # Details column. Parse first, then decide.
    raw_body = resp.text or ""
    body_snippet = raw_body[:600]
    parsed: Any = None
    try:
        parsed = resp.json()
    except (ValueError, httpx.DecodingError):
        parsed = None

    if isinstance(parsed, dict) and parsed.get("ok") is True:
        return LanguageSyncOneResult(
            domain_name=domain.name,
            domain_id=domain.id,
            ok=True,
            status_code=resp.status_code,
            detail=body_snippet,
            elapsed_ms=elapsed,
        )

    # Failure path. Build a useful detail rather than dumping raw HTML —
    # surfaces (1) the upstream's JSON `error` if any, (2) the cf-ray /
    # WWW-Authenticate headers that help diagnose Cloudflare or rate-limit
    # blocks when the upstream returns the same opaque 401 for every input,
    # (3) a hint when the body isn't JSON at all (e.g. homepage HTML —
    # endpoint not installed).
    if isinstance(parsed, dict):
        upstream_err = parsed.get("error") or parsed.get("message")
        prefix = f"{upstream_err}" if upstream_err else body_snippet
    else:
        # Non-JSON body. Likely the homepage rendered after a silent
        # query-string ignore, or an HTML error page.
        looks_like_html = raw_body.lstrip().lower().startswith(("<!doctype", "<html"))
        if looks_like_html:
            prefix = (
                "Upstream returned HTML, not JSON — the __add_language=1 "
                "endpoint is probably not installed on this site."
            )
        else:
            prefix = body_snippet or "Empty response body"

    diag_bits: list[str] = []
    cf_ray = resp.headers.get("cf-ray")
    if cf_ray:
        diag_bits.append(f"cf-ray={cf_ray}")
    www_auth = resp.headers.get("www-authenticate")
    if www_auth:
        diag_bits.append(f"WWW-Authenticate={www_auth}")
    diag = f" [{'; '.join(diag_bits)}]" if diag_bits else ""

    detail = f"{prefix}{diag}"

    return LanguageSyncOneResult(
        domain_name=domain.name,
        domain_id=domain.id,
        ok=False,
        status_code=resp.status_code,
        detail=detail[:600],
        elapsed_ms=elapsed,
    )
