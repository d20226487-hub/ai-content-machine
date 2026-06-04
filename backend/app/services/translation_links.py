"""Translation-link localization + expected-link computation.

The Link Checker's 3rd mode ("Check Translation Links") doesn't read expected
links from a column — it COMPUTES them. For each row it takes the links in the
ORIGINAL content and produces the link each should become in the TRANSLATION
for that row's language, by inserting the language as a subfolder right after
the domain (``site.com/foo`` → ``site.com/es/foo``) under a per-type treatment:

  * product  — always localize, EXCEPT pages listed as per-language exceptions
               (those keep the root URL).
  * internal — localize OR skip (user choice).
  * external — localize OR skip (user choice).

A link's type is decided by domains, not paths: links whose host matches a
given PRODUCT domain are products; links whose host matches the row's INTERNAL
domains (read from user-chosen columns — each row carries its own site domain)
are internal; everything else is external. Product is checked first so a
product domain that also appears among the internal columns still wins.

These are pure functions — no DB, no I/O — so they're trivially testable and
reused by both the seed (materialize the expected column + juxtapose) and any
future preview. URL handling leans on ``urllib.parse``; link extraction reuses
the checker's structured extractor so original-content links parse the same way
everywhere.
"""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from app.services.link_check import extract_output_links, normalize_link

LinkType = Literal["product", "internal", "external"]
Treatment = Literal["skip", "localize"]

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)


# ---------- config parsing (raw textarea → normalized lists) ----------


def _split_lines(text: str | None) -> list[str]:
    """Split a bulk-pasted textarea into trimmed, non-empty tokens.

    Accepts newline- or comma-separated input so paste-from-spreadsheet and
    paste-from-list both work."""
    if not text:
        return []
    parts = re.split(r"[\n,]+", text)
    return [p.strip() for p in parts if p.strip()]


def normalize_domain(d: str) -> str:
    """User-entered domain → bare comparable host (no scheme/www/path/port)."""
    s = d.strip().lower()
    s = _SCHEME_RE.sub("", s)
    s = s.split("/", 1)[0]
    s = s.split("@")[-1]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s


def parse_domains(text: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for tok in _split_lines(text):
        d = normalize_domain(tok)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def parse_exceptions(text: str | None) -> list[dict]:
    """Parse ``lang, page[, page2, …]`` lines into ``[{"lang", "page"}, …]``.

    The first comma-separated token is the language; every remaining token is
    a page (full URL, path, or slug), so one line can list several pages for
    the same language. Lines without at least one page are skipped."""
    out: list[dict] = []
    for line in (text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        lang = parts[0].lower()
        if not lang:
            continue
        for page in parts[1:]:
            if page:
                out.append({"lang": lang, "page": page})
    return out


# ---------- URL helpers ----------


def _ensure_scheme(url: str, default_host: str) -> str:
    """Best-effort absolute https URL so host/path parse cleanly downstream.

    * already-schemed → unchanged
    * protocol-relative ``//host/..`` → https
    * root-relative ``/path`` → prefix the default (first internal) host
    * bare host ``site.com/x`` → https
    * bare relative ``foo/bar`` → prefix the default host
    When no default host is known a relative URL is returned as-is (best effort).
    """
    s = url.strip()
    if not s:
        return s
    if _SCHEME_RE.match(s):
        return s
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("/"):
        return f"https://{default_host}{s}" if default_host else s
    head = s.split("/", 1)[0]
    if "." in head and " " not in head:
        return "https://" + s  # bare host
    return f"https://{default_host}/{s}" if default_host else s


def _host_of(url: str) -> str:
    """Lowercased registrable-ish host (strip credentials/port/www)."""
    s = url if _SCHEME_RE.match(url) else "https://" + url
    netloc = (urlsplit(s).netloc or "").lower()
    netloc = netloc.split("@")[-1].split(":", 1)[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def is_internal_host(host: str, internal_domains: list[str]) -> bool:
    if not host:
        return True  # relative → same site
    for d in internal_domains:
        if host == d or host.endswith("." + d):
            return True
    return False


def classify_link(
    url: str, internal_domains: list[str], product_domains: list[str]
) -> LinkType:
    """product | internal | external for an (ideally absolute) URL.

    Decided by host: a host matching a PRODUCT domain ⇒ product (checked
    first); a host matching an INTERNAL domain ⇒ internal; else external. A
    hostless (relative) link is treated as internal — same site."""
    host = _host_of(url)
    if not host:
        return "internal"
    if is_internal_host(host, product_domains):
        return "product"
    if is_internal_host(host, internal_domains):
        return "internal"
    return "external"


def localize_link(url: str, lang: str) -> str:
    """Insert ``/<lang>`` right after the host. Idempotent (won't double it).

    Requires a host to place the subfolder; a hostless URL is returned as-is.
    Query and fragment are preserved; a trailing slash is kept."""
    lang = lang.strip().strip("/")
    if not lang:
        return url
    sp = urlsplit(url if _SCHEME_RE.match(url) else "https://" + url if _host_of(url) else url)
    if not sp.netloc:
        return url
    path = sp.path or ""
    segs = [s for s in path.split("/") if s != ""]
    if segs and segs[0].lower() == lang.lower():
        return url  # already localized
    if not segs:
        new_path = f"/{lang}/"
    else:
        new_path = "/" + "/".join([lang, *segs])
        if path.endswith("/"):
            new_path += "/"
    return urlunsplit((sp.scheme, sp.netloc, new_path, sp.query, sp.fragment))


def _exc_key(s: str) -> str:
    """Normalize a page token / URL to a comparable key (no scheme/www/slashes)."""
    s = s.strip().lower()
    s = _SCHEME_RE.sub("", s)
    if s.startswith("www."):
        s = s[4:]
    s = s.split("#", 1)[0]
    return s.strip("/")


def exception_matches(url: str, lang: str, exceptions: list[dict]) -> bool:
    """True if (lang, page) lists this link. ``page`` may be a full URL, a
    path, or just the slug — matched permissively against all three forms."""
    lang = lang.strip().lower()
    sp = urlsplit(url if _SCHEME_RE.match(url) else "https://" + url)
    host = _host_of(url)
    path = (sp.path or "").strip("/").lower()
    cands = {_exc_key(url)}  # host/path
    if path:
        cands.add(path)  # products/x
        cands.add(path.split("/")[-1])  # slug
        if host:
            cands.add(f"{host}/{path}")
    for exc in exceptions:
        if exc.get("lang", "").strip().lower() != lang:
            continue
        if _exc_key(str(exc.get("page", ""))) in cands:
            return True
    return False


def expected_link_for(
    url: str,
    lang: str,
    link_type: LinkType,
    *,
    internal_treatment: Treatment,
    external_treatment: Treatment,
    exceptions: list[dict],
) -> str:
    """The link ``url`` SHOULD become in the translation for ``lang``."""
    if link_type == "product":
        if exception_matches(url, lang, exceptions):
            return url  # exception page keeps the root URL
        return localize_link(url, lang)
    if link_type == "internal":
        return localize_link(url, lang) if internal_treatment == "localize" else url
    return localize_link(url, lang) if external_treatment == "localize" else url


def compute_expected_links(
    original_text: str | None,
    lang: str,
    *,
    internal_domains: list[str],
    product_domains: list[str],
    exceptions: list[dict],
    internal_treatment: Treatment = "skip",
    external_treatment: Treatment = "skip",
) -> list[str]:
    """Expected (localized) links for one row's original content.

    ``internal_domains`` are per-row (read from the chosen domain columns);
    ``product_domains`` are the global product domain(s). Returns absolute,
    scheme-bearing URLs (deduped, order-preserving) so the materialized
    expected column parses under the checker's expected-link extractor and
    juxtaposes cleanly against the translation."""
    lang = (lang or "").strip()
    if not lang:
        return []
    internal_domains = [normalize_domain(d) for d in internal_domains]
    product_domains = [normalize_domain(d) for d in product_domains]
    exceptions = exceptions or []
    default_host = (
        internal_domains[0]
        if internal_domains
        else (product_domains[0] if product_domains else "")
    )

    out: list[str] = []
    seen: set[str] = set()
    for raw in extract_output_links(original_text):
        absu = _ensure_scheme(raw, default_host)
        link_type = classify_link(absu, internal_domains, product_domains)
        expected = expected_link_for(
            absu,
            lang,
            link_type,
            internal_treatment=internal_treatment,
            external_treatment=external_treatment,
            exceptions=exceptions,
        )
        if expected not in seen:
            seen.add(expected)
            out.append(expected)
    return out


def _strip_first_seg(nlink: str) -> str:
    """Drop a normalized link's first path segment (its would-be language
    prefix): ``host/xx/a/b`` → ``host/a/b``; ``host/xx`` → ``host``."""
    parts = nlink.split("/", 2)
    if len(parts) < 2:
        return nlink
    if len(parts) == 2:
        return parts[0]
    return parts[0] + "/" + parts[2]


def compute_row_breakdown(
    original_text: str | None,
    translated_text: str | None,
    lang: str,
    *,
    internal_domains: list[str],
    product_domains: list[str],
    exceptions: list[dict],
    internal_treatment: Treatment = "skip",
    external_treatment: Treatment = "skip",
) -> dict:
    """The raw-table breakdown for one row (computed on demand).

    Returns: ``original`` links; ``translation`` links each tagged
    ok/discrepancy/invented; and ``aligned`` — one entry per expected link
    paired with the WRONG translation link it should have been (``wrong`` is
    None when the translation got it right or simply omitted it), plus a
    trailing entry per invented (made-up) translation link with
    ``expected=None``. The pairing lets the UI align each red link on the same
    row as its expected link."""
    lang = (lang or "").strip()
    internal_domains = [normalize_domain(d) for d in internal_domains]
    product_domains = [normalize_domain(d) for d in product_domains]
    default_host = (
        internal_domains[0]
        if internal_domains
        else (product_domains[0] if product_domains else "")
    )

    # Original links + their expected counterpart + link type (keep the
    # original→expected map so each wrong translation link can be paired with
    # its expected one, and carry the type for the link-type filter).
    original: list[str] = []
    seen_o: set[str] = set()
    pairs: list[tuple[str, str, str]] = []  # (original_norm, expected_url, type)
    seen_e: set[str] = set()
    for raw in extract_output_links(original_text):
        absu = _ensure_scheme(raw, default_host)
        if absu not in seen_o:
            seen_o.add(absu)
            original.append(absu)
        if not lang:
            continue
        ltype = classify_link(absu, internal_domains, product_domains)
        e = expected_link_for(
            absu,
            lang,
            ltype,
            internal_treatment=internal_treatment,
            external_treatment=external_treatment,
            exceptions=exceptions,
        )
        if e not in seen_e:
            seen_e.add(e)
            pairs.append((normalize_link(absu), e, ltype))

    expected_norm = {normalize_link(e) for (_o, e, _t) in pairs}
    orig_norm_set = {o for (o, _e, _t) in pairs}

    translation = extract_output_links(translated_text)
    translation_norm = {normalize_link(t) for t in translation}

    tagged_trans: list[dict] = []
    wrong_by_orig: dict[str, dict] = {}  # original_norm → first wrong link
    invented: list[dict] = []
    for t in translation:
        nt = normalize_link(t)
        if nt in expected_norm:
            tagged_trans.append({"url": t, "kind": "ok"})
        elif nt in orig_norm_set or _strip_first_seg(nt) in orig_norm_set:
            tag = {"url": t, "kind": "discrepancy"}
            tagged_trans.append(tag)
            o = nt if nt in orig_norm_set else _strip_first_seg(nt)
            wrong_by_orig.setdefault(o, tag)
        else:
            tag = {"url": t, "kind": "invented"}
            tagged_trans.append(tag)
            invented.append(tag)

    # One aligned entry per expected link (its wrong counterpart if any), then
    # the invented links (no expected).
    aligned: list[dict] = []
    for (o, e, ltype) in pairs:
        wrong = None if normalize_link(e) in translation_norm else wrong_by_orig.get(o)
        aligned.append({"expected": e, "wrong": wrong, "link_type": ltype})
    for inv in invented:
        # Made-up links still fall into one of the 3 types by their own host.
        aligned.append(
            {
                "expected": None,
                "wrong": inv,
                "link_type": classify_link(inv["url"], internal_domains, product_domains),
            }
        )

    return {
        "original": original,
        "translation": tagged_trans,
        "aligned": aligned,
    }
