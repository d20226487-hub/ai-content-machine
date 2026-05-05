"""WordPress REST client. Auth: Application Passwords (Basic auth)."""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.cms.base import CmsClient, PublishResult, TestResult
from app.core.ssrf import (
    SafeAsyncTransport,
    UnsafeUrlError,
    stream_to_buffer,
    validate_public_url,
)

# Standard WP REST fields (i.e. NOT custom meta). Anything not in this set
# OR not flagged as is_meta=True falls into the meta dict.
STANDARD_WP_FIELDS = {
    "title",
    "content",
    "excerpt",
    "slug",
    "status",
    "categories",
    "tags",
    "featured_media",
    "author",
    "date",
    "comment_status",
    "ping_status",
    "format",
    "sticky",
    "template",
}


class WordPressClient(CmsClient):
    cms_type = "wordpress"

    def __init__(
        self,
        *,
        base_url: str,
        credentials: str | None,
        publish_config: dict | None = None,
        multilingual_plugin: str = "none",
        media_cache=None,  # services.media_cache.MediaCache | None
    ) -> None:
        super().__init__(base_url=base_url, credentials=credentials)
        self.publish_config = publish_config or {}
        self.multilingual_plugin = multilingual_plugin
        self._media_cache = media_cache

    def _auth_header(self) -> dict[str, str]:
        if not self.credentials:
            return {}
        # Stored as "user:application_password"
        token = base64.b64encode(self.credentials.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    async def test_connection(self) -> TestResult:
        url = f"{self.base_url}/wp-json/wp/v2/posts?per_page=1&context=edit"
        start = time.perf_counter()
        try:
            validate_public_url(url)
            async with httpx.AsyncClient(
                timeout=15.0, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.get(url, headers=self._auth_header())
            elapsed = int((time.perf_counter() - start) * 1000)

            if resp.status_code == 200:
                return TestResult(
                    ok=True,
                    status_code=200,
                    detail="WordPress reachable; credentials accepted.",
                    elapsed_ms=elapsed,
                )
            if resp.status_code in (401, 403):
                return TestResult(
                    ok=False,
                    status_code=resp.status_code,
                    detail=(
                        "Authentication rejected. Check user + Application Password."
                    ),
                    elapsed_ms=elapsed,
                )
            if resp.status_code == 404:
                return TestResult(
                    ok=False,
                    status_code=404,
                    detail=(
                        "REST API not found at /wp-json/wp/v2/posts. "
                        "Is this a WordPress site with REST enabled?"
                    ),
                    elapsed_ms=elapsed,
                )
            return TestResult(
                ok=False,
                status_code=resp.status_code,
                detail=f"Unexpected HTTP {resp.status_code}: {resp.text[:200]}",
                elapsed_ms=elapsed,
            )
        except UnsafeUrlError as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            return TestResult(
                ok=False,
                status_code=None,
                detail=f"URL rejected: {e}",
                elapsed_ms=elapsed,
            )
        except httpx.HTTPError as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            return TestResult(
                ok=False,
                status_code=None,
                detail=f"Network error: {e}",
                elapsed_ms=elapsed,
            )

    def _resolve_profile(self, profile_name: str | None) -> tuple[str, list[dict]]:
        """Return (post_type, field_defs) for the named profile.

        Backward-compat: if ``publish_config`` is the legacy
        ``{post_type, fields}`` shape (no ``profiles`` key), it is treated as
        a single profile named "Default".
        """
        cfg = self.publish_config or {}
        profiles = cfg.get("profiles")
        if isinstance(profiles, list) and profiles:
            chosen: dict | None = None
            if profile_name:
                chosen = next(
                    (p for p in profiles if isinstance(p, dict) and p.get("name") == profile_name),
                    None,
                )
            if chosen is None:
                chosen = next((p for p in profiles if isinstance(p, dict)), None)
            if chosen is not None:
                return (chosen.get("post_type") or "posts", chosen.get("fields") or [])
        # Legacy shape, or empty config.
        return (cfg.get("post_type") or "posts", cfg.get("fields") or [])

    async def publish_post(
        self,
        *,
        fields: dict[str, Any],
        language: str | None = None,
        profile_name: str | None = None,
    ) -> PublishResult:
        """Build a WP REST payload from the form fields and POST it.

        Field placement is driven by the profile's ``fields[*]``:
          - is_meta=True → goes under `meta[meta_key]`
          - taxonomy_ids type → cast value (comma list or list) to int[]
            and place under the field's `key` (e.g. "categories", "tags",
            or a custom taxonomy slug).
          - media_url type → numeric value used as ID; URL value is
            downloaded and uploaded to /wp-json/wp/v2/media; failure
            surfaces as a non-fatal warning so the rest of the post survives.
          - everything else with key in STANDARD_WP_FIELDS → top-level.
          - any other key → silently dropped (custom non-meta fields aren't
            supported by stock WP REST without registering them).
        """
        post_type, field_defs = self._resolve_profile(profile_name)
        defs_by_key = {f["key"]: f for f in field_defs if isinstance(f, dict) and f.get("key")}

        body: dict[str, Any] = {}
        meta: dict[str, Any] = {}
        warnings: list[str] = []

        media_uploads: list[tuple[str, str]] = []  # [(field_key, url)]

        for key, value in fields.items():
            if value is None or value == "":
                continue
            d = defs_by_key.get(key, {"key": key, "type": "text"})
            ftype = d.get("type", "text")
            is_meta = bool(d.get("is_meta"))

            if is_meta:
                meta_key = d.get("meta_key") or key
                meta[meta_key] = value
                continue

            if ftype == "taxonomy_ids":
                ids = _coerce_id_list(value)
                if ids:
                    body[key] = ids
                continue

            if ftype == "media_url":
                s = str(value).strip()
                if s.isdigit():
                    body[key] = int(s)
                elif s.startswith("http://") or s.startswith("https://"):
                    # Defer the upload so we don't await inside this loop more than necessary.
                    media_uploads.append((key, s))
                else:
                    warnings.append(
                        f"Field {key!r}: value is neither a numeric media ID nor a URL — skipped."
                    )
                continue

            # text / textarea / select / unrecognized → top-level if standard,
            # else meta under the same key.
            if key in STANDARD_WP_FIELDS:
                # WP REST wants {"raw": "..."} for title and content if you
                # need raw HTML; the simple string form is accepted too.
                body[key] = value
            else:
                meta[key] = value

        # Now resolve any media-URL uploads. Failures are non-fatal: we add a
        # warning and skip the field so the rest of the post still gets posted.
        for key, url in media_uploads:
            try:
                media_id = await self._upload_media_from_url(url)
                body[key] = media_id
            except Exception as e:
                warnings.append(f"Featured image upload failed for {url!r}: {e}")

        if meta:
            body["meta"] = meta

        # Multilingual: Polylang accepts ?lang=, WPML uses different routes.
        params: dict[str, Any] = {}
        if language and self.multilingual_plugin == "polylang":
            params["lang"] = language
        # WPML translation linking is Phase 4.

        url = f"{self.base_url}/wp-json/wp/v2/{post_type}"
        try:
            validate_public_url(url)
            async with httpx.AsyncClient(
                timeout=30.0, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.post(
                    url,
                    json=body,
                    params=params,
                    headers={**self._auth_header(), "Content-Type": "application/json"},
                )
        except UnsafeUrlError as e:
            return PublishResult(
                ok=False,
                status_code=None,
                payload_sent=body,
                response_json=None,
                cms_post_id=None,
                cms_post_url=None,
                error=f"URL rejected: {e}",
                warnings=warnings,
            )
        except httpx.HTTPError as e:
            return PublishResult(
                ok=False,
                status_code=None,
                payload_sent=body,
                response_json=None,
                cms_post_id=None,
                cms_post_url=None,
                error=f"Network error: {e}",
                warnings=warnings,
            )

        try:
            resp_json = resp.json() if resp.content else None
        except ValueError:
            resp_json = None

        if 200 <= resp.status_code < 300 and isinstance(resp_json, dict):
            return PublishResult(
                ok=True,
                status_code=resp.status_code,
                payload_sent=body,
                response_json=resp_json,
                cms_post_id=str(resp_json.get("id")) if resp_json.get("id") is not None else None,
                cms_post_url=resp_json.get("link"),
                error=None,
                warnings=warnings,
            )

        # WP errors usually look like {"code": "...", "message": "...", "data": {...}}
        msg = ""
        if isinstance(resp_json, dict):
            msg = str(resp_json.get("message") or resp_json.get("code") or "")
        if not msg:
            msg = (resp.text or "")[:300]
        return PublishResult(
            ok=False,
            status_code=resp.status_code,
            payload_sent=body,
            response_json=resp_json if isinstance(resp_json, dict) else None,
            cms_post_id=None,
            cms_post_url=None,
            error=f"WP returned HTTP {resp.status_code}: {msg}",
            warnings=warnings,
        )

    async def _upload_media_from_url(self, source_url: str) -> int:
        """Download an image from `source_url` and upload it to WP media.

        Returns the new media ID. Raises on any failure.
        Limits: 30s total timeout, 15MB max body size.

        If a MediaCache was provided, the cache is checked first; on hit we
        skip the download and upload entirely. On miss we upload normally
        and store the result for future reuse.
        """
        if self._media_cache is not None:
            cached = await self._media_cache.lookup(source_url)
            if cached is not None:
                return cached

        max_bytes = 15 * 1024 * 1024
        # Pre-validate the source URL. ``follow_redirects=True`` is still set
        # below — SafeAsyncTransport revalidates each redirect hop, so a 302 to
        # http://169.254.169.254 won't be followed.
        try:
            validate_public_url(source_url)
        except UnsafeUrlError as e:
            raise RuntimeError(f"source URL rejected: {e}") from e

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            transport=SafeAsyncTransport(),
        ) as client:
            # Stream the download so an attacker can't push us into a 1GB body.
            async with client.stream("GET", source_url) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"source returned HTTP {r.status_code}")
                content_type = (
                    r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    or "image/jpeg"
                )
                try:
                    body_bytes = await stream_to_buffer(r, max_bytes=max_bytes)
                except UnsafeUrlError as e:
                    raise RuntimeError(str(e)) from e

            # Derive a filename from the URL path
            from urllib.parse import urlparse

            path = urlparse(source_url).path
            filename = path.rsplit("/", 1)[-1] or "image.jpg"
            # Sanity-strip query suffixes that survived urlparse (none should, but be safe)
            filename = filename.split("?")[0] or "image.jpg"

            # Upload to WP
            up = await client.post(
                f"{self.base_url}/wp-json/wp/v2/media",
                content=body_bytes,
                headers={
                    **self._auth_header(),
                    "Content-Type": content_type,
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
            if up.status_code >= 300:
                detail = ""
                try:
                    detail = (up.json() or {}).get("message", "")
                except ValueError:
                    detail = (up.text or "")[:200]
                raise RuntimeError(f"WP /media returned HTTP {up.status_code}: {detail}")
            try:
                up_json = up.json()
            except ValueError as e:
                raise RuntimeError(f"WP /media returned non-JSON: {e}") from e
            mid = up_json.get("id") if isinstance(up_json, dict) else None
            if not isinstance(mid, int):
                raise RuntimeError("WP /media response missing integer 'id'")

            if self._media_cache is not None:
                try:
                    await self._media_cache.remember(
                        source_url,
                        mid,
                        content_type=content_type,
                        size_bytes=len(body_bytes),
                    )
                except Exception:
                    # Cache failures must not break the publish.
                    pass

            return mid


def _coerce_id_list(value: Any) -> list[int]:
    """Accept '1,2,3' or [1,'2',3] → [1, 2, 3]. Drops non-numeric tokens."""
    items: list[Any]
    if isinstance(value, list):
        items = value
    else:
        items = [s.strip() for s in str(value).split(",") if s.strip()]
    out: list[int] = []
    for it in items:
        try:
            out.append(int(it))
        except (TypeError, ValueError):
            continue
    return out
