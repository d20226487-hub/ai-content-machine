"""Link extraction, juxtaposition, and crawling for the Link Checker tool.

Three problem classes the checker surfaces:
  * omitted      — an expected link (from the per-row expected column) is
                   absent from the output column(s)
  * hallucinated — an output link is not in the expected set
  * broken       — an output link returns a non-OK HTTP status (typo / dead)

Extraction is intentionally split:
  * ``extract_output_links`` pulls STRUCTURED links — ``href``/``src``
    attributes and markdown ``[text](url)`` — the way a model emits them in
    generated HTML.
  * ``extract_expected_links`` is permissive — the expected column is hand-
    authored, so links may be bare and scheme-less ("site.com/a"), comma or
    newline separated.

Comparison is scheme/www/trailing-slash/fragment-insensitive
(``normalize_link``) so "site.com/a" and "https://www.site.com/a/" are
treated as the same link — those differences are rarely the actual error.
"""
from __future__ import annotations

import asyncio
import re

import httpx

from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url

# href="..." / src='...'
_ATTR_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# [label](url ...) — stop at whitespace or ) so titles don't leak in
_MD_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")
# Permissive URL-ish token: optional scheme, a dotted host, optional path.
_BARE_RE = re.compile(
    r"""(?:https?://)?(?:[\w-]+\.)+[a-z]{2,}(?:/[^\s,;"'<>)\]]*)?""",
    re.IGNORECASE,
)

# Sanity bound on UNIQUE links per run. The crawl is distributed across
# workers now, so this is far higher than the old single-task cap.
_MAX_CRAWL_LINKS = 50000
# Unique links per fan-out child task. ~100 keeps each child a few crawl
# sub-batches long so a crash loses little and chunks spread across workers.
LINK_CHUNK_SIZE = 100


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def extract_output_links(text: str | None) -> list[str]:
    """Structured links from generated content: href/src + markdown."""
    if not text:
        return []
    found = [m.group(1).strip() for m in _ATTR_RE.finditer(text)]
    found += [m.group(1).strip() for m in _MD_RE.finditer(text)]
    return _dedupe([u for u in found if _looks_like_link(u)])


def extract_expected_links(text: str | None) -> list[str]:
    """Permissive extraction for the hand-authored expected column."""
    if not text:
        return []
    found = [m.group(0).strip() for m in _BARE_RE.finditer(text)]
    return _dedupe([u for u in found if _looks_like_link(u)])


def _looks_like_link(u: str) -> bool:
    if not u:
        return False
    low = u.lower()
    if low.startswith(("mailto:", "tel:", "#", "javascript:", "data:")):
        return False
    if low.startswith(("http://", "https://")):
        return True
    # bare host like "site.com/a" — must contain a dot before any slash
    head = u.split("/", 1)[0]
    return "." in head and " " not in head


def normalize_link(u: str) -> str:
    """Comparison key: lowercase, drop scheme / leading www / fragment, and
    a single trailing slash. Query is preserved (it can be meaningful)."""
    s = u.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("#", 1)[0]
    if s.endswith("/"):
        s = s[:-1]
    return s


def crawlable_url(u: str) -> str:
    """A fetchable absolute URL — prepend https:// when scheme-less."""
    s = u.strip()
    if not re.match(r"^https?://", s, re.IGNORECASE):
        s = "https://" + s
    return s


def juxtapose(
    output_links: list[str], expected_links: list[str]
) -> tuple[list[str], list[str]]:
    """Return ``(omitted, hallucinated)``.

    omitted      — expected links whose normalized form isn't among outputs.
    hallucinated — output links whose normalized form isn't among expected.
    Returns the ORIGINAL link strings (not normalized) for display.
    """
    out_norm = {normalize_link(u) for u in output_links}
    exp_norm = {normalize_link(u) for u in expected_links}
    omitted = [u for u in expected_links if normalize_link(u) not in out_norm]
    hallucinated = [u for u in output_links if normalize_link(u) not in exp_norm]
    return omitted, hallucinated


# ---------- crawling ----------


CRAWL_CONCURRENCY = 10
CRAWL_TIMEOUT = 8.0
# Process the unique-link set in batches so the worker can persist progress
# and observe a Cancel between batches (all DB I/O stays in the task, never
# inside a concurrent gather worker).
CRAWL_BATCH = 50


class LinkStatus:
    """Result of crawling one URL. ``ok`` True means a healthy 2xx/3xx.

    ``detail_code`` is a stable token the frontend localizes:
    'http_error' | 'timeout' | 'unreachable' | 'blocked' | 'ok' | 'redirect'.
    """

    def __init__(self, ok: bool, status_code: int | None, detail_code: str):
        self.ok = ok
        self.status_code = status_code
        self.detail_code = detail_code


def make_crawl_client() -> httpx.AsyncClient:
    """httpx client wrapped in the SSRF-safe transport (re-validates every
    redirect hop). Caller manages its lifecycle with ``async with``."""
    return httpx.AsyncClient(
        transport=SafeAsyncTransport(),
        timeout=CRAWL_TIMEOUT,
        limits=httpx.Limits(max_connections=CRAWL_CONCURRENCY),
        headers={"User-Agent": "ContentBeast-LinkChecker/1.0"},
    )


async def check_url(client: httpx.AsyncClient, url: str) -> LinkStatus:
    fetch_url = crawlable_url(url)
    # Block SSRF up front (the transport re-checks each redirect hop too).
    # A DNS-resolution failure here is NOT a security block — it's a dead or
    # typo'd domain, which is exactly a link problem we want to report.
    try:
        validate_public_url(fetch_url)
    except UnsafeUrlError as e:
        if "could not resolve" in str(e).lower():
            return LinkStatus(False, None, "unreachable")
        return LinkStatus(False, None, "blocked")
    try:
        r = await client.head(fetch_url, follow_redirects=True)
        # Many servers mishandle HEAD (405/501) — confirm with a GET.
        if r.status_code >= 400:
            r = await client.get(fetch_url, follow_redirects=True)
        code = r.status_code
        if code < 400:
            # r.history is non-empty when one or more redirects were followed.
            return LinkStatus(True, code, "redirect" if r.history else "ok")
        return LinkStatus(False, code, "http_error")
    except httpx.TimeoutException:
        return LinkStatus(False, None, "timeout")
    except UnsafeUrlError:
        return LinkStatus(False, None, "blocked")
    except httpx.HTTPError:
        return LinkStatus(False, None, "unreachable")


async def crawl_batch(
    client: httpx.AsyncClient, urls: list[str]
) -> dict[str, LinkStatus]:
    """Crawl one batch of unique URLs concurrently → ``{url: LinkStatus}``."""
    sem = asyncio.Semaphore(CRAWL_CONCURRENCY)
    results: dict[str, LinkStatus] = {}

    async def one(u: str) -> None:
        async with sem:
            results[u] = await check_url(client, u)

    await asyncio.gather(*(one(u) for u in urls))
    return results
