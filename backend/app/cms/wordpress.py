"""WordPress REST client. Auth: Application Passwords (Basic auth)."""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.cms.base import CmsClient, PublishResult, TestResult
from app.core.ssrf import (
    SafeAsyncTransport,
    UnsafeUrlError,
    stream_to_buffer,
    validate_public_url,
)

# Sent with every WP request. A realistic UA bypasses most Cloudflare /
# WAF "block known bots" rules that flag the default ``python-httpx/...``
# string. Includes a project identifier so admins reading server logs can
# trace the traffic back to us.
_USER_AGENT = (
    "Mozilla/5.0 (compatible; AI-Content-Machine/1.0; "
    "+bulk-publisher)"
)


@dataclass
class LookupResult:
    """Outcome of `find_post`. ``post_id`` is set on a hit; ``error`` is
    set when the lookup failed for reasons other than "no results found"
    (HTTP error, WAF block, malformed JSON). Both None means the request
    succeeded but returned zero results — the typical "slug doesn't
    exist" case.
    """

    post_id: int | None = None
    error: str | None = None

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
            return {"User-Agent": _USER_AGENT}
        # Stored as "user:application_password". Normalize whitespace
        # around the colon — a natural paste pattern is "user: app_pass"
        # (with a space after the colon) which silently broke auth on
        # Custom CMS and would break here too. Splitting on the FIRST
        # colon + stripping each half handles the common case; a colon-
        # less paste passes through unchanged so the upstream can return
        # a sensible error rather than us silently rewriting it.
        login, sep, password = self.credentials.partition(":")
        clean = f"{login.strip()}:{password.strip()}" if sep else self.credentials
        token = base64.b64encode(clean.encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "User-Agent": _USER_AGENT,
        }

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

    async def find_post(
        self,
        *,
        post_type: str,
        lookup_kind: str,
        value: str,
        language: str | None = None,
    ) -> LookupResult:
        """Resolve an existing WP post to its numeric ID.

        Returns a ``LookupResult`` so the caller can distinguish "no rows
        found" (the slug really doesn't exist) from "the request was
        blocked / errored out" (Cloudflare WAF, 5xx, malformed JSON).

        - ``lookup_kind='id'`` — accept a numeric value as-is (no HTTP call).
        - ``lookup_kind='slug'`` — extract the slug from the value (URL or
          plain slug both accepted), then query
          ``GET /wp-json/wp/v2/{post_type}?slug=…&status=any&_fields=id``
          and return the first hit's id. We try ``context=view`` first
          (works without elevated caps + is friendlier to WAF rules) and
          only fall back to ``context=edit`` when zero rows come back —
          ``context=edit`` is what lets us see non-publish statuses.
        """
        v = (value or "").strip()
        if not v:
            return LookupResult(error="empty lookup value")
        if lookup_kind == "id":
            try:
                n = int(v)
            except (TypeError, ValueError):
                return LookupResult(error=f"value {v!r} is not a numeric id")
            return LookupResult(post_id=n) if n >= 0 else LookupResult(
                error=f"negative id {n}"
            )

        # ----- slug -----
        slug = _extract_slug(v)
        if not slug:
            return LookupResult(error=f"could not extract a slug from {v!r}")

        url = f"{self.base_url}/wp-json/wp/v2/{post_type}"
        # Polylang accepts `?lang=` like the publish path does. Without it,
        # a site with same-slug-in-different-languages would return the
        # default-language post, and Update mode would PATCH the wrong one.
        # WPML 4.x also respects `?lang=` (older versions ignore it — best
        # effort). For domains with multilingual_plugin='none' we skip
        # the param entirely.
        extra_params: dict[str, str] = {}
        if language and self.multilingual_plugin in {"polylang", "wpml"}:
            extra_params["lang"] = language
        # First pass — view context, no auth-elevated fields. Less likely
        # to trip Cloudflare WAF rules that flag authenticated requests.
        first = await self._slug_query(
            url, slug=slug, context="view", extra_params=extra_params,
        )
        if first.post_id is not None or first.error is not None:
            return first
        # Zero rows. Retry with context=edit so drafts / private posts
        # become visible. This needs the Basic auth cap; if Cloudflare
        # blocks it, we surface that error instead of falling through
        # silently as "not found".
        return await self._slug_query(
            url, slug=slug, context="edit", extra_params=extra_params,
        )

    async def _slug_query(
        self,
        url: str,
        *,
        slug: str,
        context: str,
        extra_params: dict[str, str] | None = None,
    ) -> LookupResult:
        """Do one GET to /wp/v2/{type}?slug=... and classify the result.

        - 200 + non-empty list → ``post_id`` set.
        - 200 + empty list      → both None (call site distinguishes
                                  "retry with elevated context" from
                                  "really not found").
        - anything else         → ``error`` set with status + body
                                  excerpt so the user sees the real
                                  reason (e.g. "Cloudflare 403 — bot
                                  challenge").
        """
        try:
            validate_public_url(url)
            async with httpx.AsyncClient(
                timeout=15.0, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.get(
                    url,
                    params={
                        "slug": slug,
                        "status": "any",
                        "_fields": "id",
                        "per_page": 1,
                        "context": context,
                        **(extra_params or {}),
                    },
                    headers=self._auth_header(),
                )
        except UnsafeUrlError as e:
            return LookupResult(error=f"URL rejected: {e}")
        except httpx.HTTPError as e:
            return LookupResult(error=f"network error: {e}")

        if resp.status_code != 200:
            excerpt = ""
            try:
                # Try JSON first — WP errors are usually structured.
                j = resp.json()
                if isinstance(j, dict):
                    excerpt = str(j.get("message") or j.get("code") or "")
            except ValueError:
                # Probably an HTML error page (Cloudflare, WAF, nginx).
                excerpt = (resp.text or "")[:200].strip().replace("\n", " ")
            # Cloudflare returns 403 with a CF-Ray header — surface that
            # so users can paste it into Cloudflare support if needed.
            cf_ray = resp.headers.get("CF-Ray") or resp.headers.get("cf-ray")
            extras = f" (CF-Ray: {cf_ray})" if cf_ray else ""
            return LookupResult(
                error=(
                    f"HTTP {resp.status_code} from /wp-json/wp/v2 "
                    f"(context={context}){extras}. "
                    + (
                        f"Cloudflare / WAF block — request never reached "
                        f"WordPress. Allowlist the API server's outbound IP "
                        f"in Cloudflare, disable Bot Fight Mode on /wp-json/*, "
                        f"or relax the 'WordPress' managed ruleset. "
                        if resp.status_code == 403
                        else ""
                    )
                    + (f"Body: {excerpt!r}" if excerpt else "")
                ).strip()
            )
        try:
            data = resp.json()
        except ValueError:
            return LookupResult(
                error=f"HTTP 200 but non-JSON response (context={context})"
            )
        if not isinstance(data, list) or not data:
            # Real "not found" — both None lets the caller decide whether
            # to retry with a different context.
            return LookupResult()
        first = data[0]
        if not isinstance(first, dict):
            return LookupResult()
        pid = first.get("id")
        return (
            LookupResult(post_id=int(pid))
            if isinstance(pid, int)
            else LookupResult()
        )

    async def update_post(
        self,
        *,
        post_id: int,
        fields: dict[str, Any],
        language: str | None = None,
        profile_name: str | None = None,
    ) -> PublishResult:
        """PATCH an existing WP post.

        WP REST uses ``POST /wp/v2/{post_type}/{id}`` with PATCH-merge
        semantics: keys you send overwrite, keys you omit are unchanged.

        Empty / None field values are filtered out at body-build time
        (same as create), so "blank cell = leave unchanged" works
        naturally on the spreadsheet side.
        """
        return await self._send_post(
            fields=fields,
            language=language,
            profile_name=profile_name,
            existing_post_id=post_id,
        )

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
        return await self._send_post(
            fields=fields,
            language=language,
            profile_name=profile_name,
            existing_post_id=None,
        )

    async def _send_post(
        self,
        *,
        fields: dict[str, Any],
        language: str | None,
        profile_name: str | None,
        existing_post_id: int | None,
    ) -> PublishResult:
        """Shared body-build + HTTP call for create + update.

        When ``existing_post_id`` is None the target is
        ``POST /wp-json/wp/v2/{post_type}`` (create).
        When it's set the target is ``POST /wp-json/wp/v2/{post_type}/{id}``
        which WP treats as PATCH-merge (omitted keys are preserved on the
        server). Field-mapping logic is identical in both cases — the only
        difference is the URL and that a 200 with the existing id is
        considered success.
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

        if existing_post_id is not None:
            url = f"{self.base_url}/wp-json/wp/v2/{post_type}/{existing_post_id}"
        else:
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


def _extract_slug(value: str) -> str:
    """Turn a URL or path into a bare WP slug.

    Accepts ``https://site.com/category/foo-bar/``, ``/foo-bar``, or a
    plain ``foo-bar`` — all return ``foo-bar``. Query strings and trailing
    slashes are dropped. Returns "" when the input is empty or whitespace
    so the caller can surface a "not found" failure consistently.
    """
    from urllib.parse import urlparse

    v = (value or "").strip()
    if not v:
        return ""
    # Strip a query string if any.
    v = v.split("?", 1)[0].split("#", 1)[0]
    # If it looks like a URL, take just the path. Otherwise treat the whole
    # thing as a path.
    if "://" in v:
        try:
            v = urlparse(v).path
        except ValueError:
            return ""
    # Walk path segments from the end, returning the first non-empty one.
    # This handles "/foo-bar", "/foo-bar/", "/category/foo-bar/", etc.
    parts = [p for p in v.split("/") if p]
    return parts[-1] if parts else ""


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
