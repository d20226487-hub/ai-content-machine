"""Custom CMS client.

Supported auth schemes:
  - bearer:           Authorization: Bearer {credentials}
  - api_key_header:   credentials JSON {"header": "X-API-Key", "value": "..."}
  - basic_auth:       Authorization: Basic base64(login:password)
                      credentials stored as the plain "login:password" string,
                      same wire format as WP Application Passwords.

test_connection() v1: HEAD against base_url. Per-domain `test_endpoint_path`
override is reserved for a future iteration.

publish_post (Phase 2): substitute {{placeholders}} in body_template with
the supplied field values, POST to base_url + endpoint_path, parse response
ID and URL using the configured dot-paths.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

import httpx

from app.cms.base import CmsClient, PublishResult, TestResult
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w\.\- ]*?)\s*\}\}")

# Sentinel returned by ``_substitute`` when a bare ``{{key}}`` placeholder
# resolves to a missing or empty value. The dict/list walkers drop any key
# whose substituted value is this sentinel, so a single body_template can
# describe a superset of every action's fields — unused keys are simply
# omitted from the outgoing payload instead of being sent as the literal
# string ``"{{id}}"`` (which the old behavior did and which upstream APIs
# either 400 on or, worse, silently store).
class _Missing:
    __slots__ = ()
    def __repr__(self) -> str:  # pragma: no cover — debug only
        return "<MISSING>"

_MISSING = _Missing()


class CustomCmsClient(CmsClient):
    cms_type = "custom"

    def __init__(
        self,
        *,
        base_url: str,
        credentials: str | None,
        auth_type: str,
        custom_config: dict | None = None,
    ) -> None:
        super().__init__(base_url=base_url, credentials=credentials)
        self.auth_type = auth_type
        self.custom_config = custom_config or {}

    def _auth_header(self) -> dict[str, str]:
        if not self.credentials:
            return {}
        if self.auth_type == "bearer":
            # A pasted token often picks up surrounding whitespace (trailing
            # newline from a copy, leading space from "Bearer xyz" being
            # pasted without the prefix). Strip both — real bearer tokens
            # don't carry whitespace.
            return {"Authorization": f"Bearer {self.credentials.strip()}"}
        if self.auth_type == "api_key_header":
            try:
                parsed = json.loads(self.credentials)
                header = str(parsed.get("header") or "")
                value = str(parsed.get("value") or "")
            except (ValueError, TypeError):
                return {}
            if not header or not value:
                return {}
            return {header.strip(): value.strip()}
        if self.auth_type == "basic_auth":
            # Credentials stored as "login:password". A natural paste
            # pattern is "login: password" (with a space after the colon)
            # which silently broke auth — the password field would carry
            # a leading space and the upstream would 401. Normalize by
            # splitting on the FIRST colon and stripping each half before
            # re-encoding. ":password" still parses as login="" /
            # password="password"; we leave that to the upstream to
            # reject. The login-doesn't-contain-colon assumption is true
            # for every CMS we talk to.
            login, sep, password = self.credentials.partition(":")
            if sep:
                clean = f"{login.strip()}:{password.strip()}"
            else:
                # No colon at all — pass through unchanged so the
                # upstream can return a sensible "malformed creds" error
                # instead of us silently rewriting the value.
                clean = self.credentials
            token = base64.b64encode(clean.encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {}

    async def test_connection(self) -> TestResult:
        test_path = (self.custom_config or {}).get("test_endpoint_path") or ""
        url = f"{self.base_url}{test_path}" if test_path else self.base_url
        start = time.perf_counter()
        try:
            validate_public_url(url)
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, transport=SafeAsyncTransport()
            ) as client:
                # HEAD when no test path configured; otherwise GET.
                if test_path:
                    resp = await client.get(url, headers=self._auth_header())
                else:
                    resp = await client.head(url, headers=self._auth_header())
            elapsed = int((time.perf_counter() - start) * 1000)
            if resp.status_code < 400:
                return TestResult(
                    ok=True,
                    status_code=resp.status_code,
                    detail=f"Reachable (HTTP {resp.status_code}).",
                    elapsed_ms=elapsed,
                )
            return TestResult(
                ok=False,
                status_code=resp.status_code,
                detail=f"HTTP {resp.status_code} from {url}.",
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

    async def publish_post(
        self,
        *,
        fields: dict[str, Any],
        language: str | None = None,
        profile_name: str | None = None,  # ignored for Custom CMS
    ) -> PublishResult:
        cfg = self.custom_config or {}
        endpoint_path = cfg.get("endpoint_path") or ""
        body_template = cfg.get("body_template") or {}

        # Bake the placeholder substitution map. `language` is exposed as
        # both {{language}} and {{lang}} so templates can use whichever name
        # matches the target API (some upstreams — like the mrba CRM — use
        # the short `lang` key in their body).
        values = dict(fields)
        if language is not None:
            values.setdefault("language", language)
            values.setdefault("lang", language)

        # ``boolean_fields`` (set by built-in page types, e.g. 'match' → "top")
        # are stored in the table as text ("true"/"false") but the upstream
        # wants a real JSON boolean. Coerce the mapped cell value here so the
        # placeholder substitutes a bool, which serializes as true/false.
        # Only mapped fields are touched — an unmapped boolean field is left
        # to the normal drop/keep logic below.
        for bfield in cfg.get("boolean_fields") or []:
            if bfield in values:
                values[bfield] = _coerce_bool(values[bfield])

        # ``send_empty_fields`` (a list of keys, set by built-in page types
        # like 'match') pins those keys into the body even when blank — empty
        # → "" instead of the default "drop the key". Other empty keys (e.g.
        # ``id`` on a create) still drop. Ordinary templates omit the key, so
        # the multi-operation drop behavior is unchanged for them.
        keep_empty = frozenset(cfg.get("send_empty_fields") or [])
        body = _substitute(body_template, values, keep_empty_keys=keep_empty)

        url = f"{self.base_url}{endpoint_path}"
        headers = {**self._auth_header(), "Content-Type": "application/json"}

        try:
            validate_public_url(url)
            async with httpx.AsyncClient(
                timeout=30.0, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except UnsafeUrlError as e:
            return PublishResult(
                ok=False,
                status_code=None,
                payload_sent=body,
                response_json=None,
                cms_post_id=None,
                cms_post_url=None,
                error=f"URL rejected: {e}",
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
            )

        try:
            resp_json = resp.json() if resp.content else None
        except ValueError:
            resp_json = None

        if 200 <= resp.status_code < 300:
            id_path = cfg.get("response_id_path") or ""
            url_path = cfg.get("response_url_path") or ""
            cms_id = _dig(resp_json, id_path) if isinstance(resp_json, (dict, list)) else None
            cms_url = _dig(resp_json, url_path) if isinstance(resp_json, (dict, list)) else None
            # APIs commonly return a relative URL ("/en/foo/"). The publish
            # history UI renders cms_post_url as a clickable anchor; relative
            # URLs would resolve against ACM's own host, which is wrong.
            # Promote any "/"-prefixed value into an absolute URL against the
            # domain's base_url. Absolute URLs and protocol-relative URLs
            # ("//host/...") pass through untouched.
            if isinstance(cms_url, str) and cms_url.startswith("/") and not cms_url.startswith("//"):
                cms_url = f"{self.base_url}{cms_url}"
            return PublishResult(
                ok=True,
                status_code=resp.status_code,
                payload_sent=body,
                response_json=resp_json if isinstance(resp_json, dict) else None,
                cms_post_id=str(cms_id) if cms_id is not None else None,
                cms_post_url=str(cms_url) if cms_url is not None else None,
                error=None,
            )

        msg = ""
        if isinstance(resp_json, dict):
            msg = str(resp_json.get("message") or resp_json.get("error") or "")
        if not msg:
            msg = (resp.text or "")[:300]
        return PublishResult(
            ok=False,
            status_code=resp.status_code,
            payload_sent=body,
            response_json=resp_json if isinstance(resp_json, dict) else None,
            cms_post_id=None,
            cms_post_url=None,
            error=f"HTTP {resp.status_code}: {msg}",
        )


_TRUTHY = {"true", "1", "yes", "y", "on", "t"}


def _coerce_bool(v: Any) -> bool:
    """Text cell → JSON boolean. ``"true"/"1"/"yes"`` (any case, trimmed) and a
    real ``True`` → True; everything else, including ``""`` and ``"false"`` →
    False. Used for page-type boolean fields (e.g. the match 'top' flag)."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in _TRUTHY


def _substitute(
    node: Any,
    values: dict[str, Any],
    *,
    keep_empty_keys: frozenset[str] = frozenset(),
) -> Any:
    """Recursively replace {{key}} placeholders inside a JSON-shaped tree.

    A scalar string consisting of exactly one placeholder is replaced with
    the typed value (so numbers/bools/objects survive). When the value is
    missing OR is an empty string, the sentinel ``_MISSING`` is returned
    so the parent container can drop the key entirely — this is what lets
    one body_template cover create / update / upsert: leave a field blank
    and it won't be sent.

    ``keep_empty_keys`` overrides that omission per dict-key: a key listed
    here stays in the body as ``""`` when its placeholder is empty/missing,
    instead of being dropped. Used by fixed-contract page types (e.g. the
    'match' page sends ``content: ""``) while still dropping the keys that
    should vanish when blank (e.g. ``id`` on a create).

    Strings containing other text (interpolation) keep the existing
    "missing → empty string" behavior because dropping a sub-section of
    a larger string would silently produce a malformed result.
    """
    if isinstance(node, str):
        match = _PLACEHOLDER.fullmatch(node.strip())
        if match:
            key = match.group(1).strip()
            v = values.get(key)
            if v is None or v == "":
                return _MISSING
            return v

        def repl(m: re.Match[str]) -> str:
            key = m.group(1).strip()
            v = values.get(key)
            return "" if v is None else str(v)

        return _PLACEHOLDER.sub(repl, node)

    if isinstance(node, list):
        out_list: list[Any] = []
        for x in node:
            r = _substitute(x, values, keep_empty_keys=keep_empty_keys)
            if r is _MISSING:
                continue
            out_list.append(r)
        return out_list

    if isinstance(node, dict):
        out_dict: dict[str, Any] = {}
        for k, v in node.items():
            r = _substitute(v, values, keep_empty_keys=keep_empty_keys)
            if r is _MISSING:
                # Drop the key — unless it's pinned to always-send, in which
                # case emit an empty string.
                if k in keep_empty_keys:
                    out_dict[k] = ""
                continue
            out_dict[k] = r
        return out_dict

    return node


def _dig(data: Any, dotted: str) -> Any:
    if not dotted:
        return None
    cur: Any = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur
