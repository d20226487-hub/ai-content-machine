"""Normalize the per-column Google Search grounding blacklist (excludeDomains).

Users paste anything — ``https://Spam.com/x``, ``www.Spam.com``, ``spam.com`` —
so reduce each entry to a bare lowercase host, drop blanks/dupes/invalid tokens,
and cap the list so a runaway paste can't exceed the tool's limit. Accepts
either a list or a free-text blob (comma / whitespace / newline separated).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Client-side safety cap on the number of excluded domains sent to the tool.
MAX_EXCLUDE_DOMAINS = 25

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]*[a-z0-9])?)+$")


def _to_host(item: str) -> str:
    """Reduce one entry to a bare, lowercased hostname ('' if not a host)."""
    s = (item or "").strip().lower()
    if not s:
        return ""
    # Give urlparse a scheme so the value lands in netloc, whether the user
    # typed a bare domain or a full URL.
    if "://" not in s:
        s = "//" + s
    host = urlparse(s).netloc
    # Strip any userinfo and port.
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host if _HOST_RE.match(host) else ""


def normalize_exclude_domains(raw) -> list[str]:
    """Return a clean, de-duplicated, capped list of bare hostnames."""
    if not raw:
        return []
    items = raw if isinstance(raw, list) else re.split(r"[\s,]+", str(raw))
    out: list[str] = []
    for item in items:
        host = _to_host(str(item))
        if host and host not in out:
            out.append(host)
            if len(out) >= MAX_EXCLUDE_DOMAINS:
                break
    return out
