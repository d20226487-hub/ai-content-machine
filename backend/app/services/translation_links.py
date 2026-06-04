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
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from app.services.link_check import extract_output_links, normalize_link

LinkType = Literal["product", "internal", "external"]
Treatment = Literal["skip", "localize"]

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)

# A leading path segment that looks like a language/locale subfolder: a
# 2-letter language code, optionally with a region or script suffix
# (``en``, ``es``, ``en-us``, ``pt-br``, ``zh-hant``). Used to tell an
# already-localized URL (``/es/foo`` → replace the ``es``) from a plain path
# (``/blog/foo`` → prepend the language). Restricted to 2-letter heads so a
# real 3+ char segment like ``/api/`` or ``/faq/`` is never mistaken for one.
_LANG_SEG_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]{2,4})?$", re.IGNORECASE)


def _is_lang_seg(seg: str) -> bool:
    return bool(_LANG_SEG_RE.match(seg))


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


def parse_default_langs(text: str | None) -> dict[str, str]:
    """Parse ``domain, lang`` (or ``domain lang``) lines into ``{domain: lang}``.

    Each product site can declare the language it serves at the ROOT — i.e. the
    language that has NO subfolder. When a link's target language equals its
    site's default, the expected link stays at the root instead of getting a
    ``/<lang>/`` prefix. Domain is normalized to a bare host; later lines win on
    a duplicate domain."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        parts = [p for p in re.split(r"[,\s]+", line.strip()) if p]
        if len(parts) < 2:
            continue
        domain = normalize_domain(parts[0])
        lang = parts[1].strip().lower().strip("/")
        if domain and lang:
            out[domain] = lang
    return out


def default_lang_for(host: str, default_langs: dict[str, str]) -> str | None:
    """The root-served language for ``host`` (exact or subdomain match), or
    None when the site isn't listed."""
    if not host or not default_langs:
        return None
    host = host.lower()
    if host in default_langs:
        return default_langs[host]
    for d, lng in default_langs.items():
        if host == d or host.endswith("." + d):
            return lng
    return None


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


def localize_link(url: str, lang: str, *, default_lang: str | None = None) -> str:
    """Place ``/<lang>`` as the first path segment, after the host.

    If the path already starts with a language subfolder, that subfolder is
    REPLACED (``site.com/es/foo`` → ``site.com/en/foo``) rather than getting a
    second one prepended (``site.com/en/es/foo``). A path with no leading
    language gets the language inserted at the front. Idempotent when the
    language is already correct.

    When ``default_lang`` is given and equals the target language, the site
    serves this language at the ROOT, so no subfolder is added — any existing
    language segment is stripped instead (``site.com/es/foo`` → ``site.com/foo``).

    Requires a host to place the subfolder; a hostless URL is returned as-is.
    Query and fragment are preserved; a trailing slash is kept."""
    lang = lang.strip().strip("/")
    if not lang:
        return url
    if default_lang and lang.lower() == default_lang.strip().lower():
        return _delocalize_link(url)  # root-served language → no subfolder
    sp = urlsplit(url if _SCHEME_RE.match(url) else "https://" + url if _host_of(url) else url)
    if not sp.netloc:
        return url
    path = sp.path or ""
    segs = [s for s in path.split("/") if s != ""]
    first_is_lang = bool(segs) and _is_lang_seg(segs[0])
    if first_is_lang and segs[0].lower() == lang.lower():
        return url  # already localized to the target language
    if not segs:
        new_path = f"/{lang}/"
    else:
        # Swap an existing language subfolder; otherwise prepend the language.
        body = segs[1:] if first_is_lang else segs
        new_path = "/" + "/".join([lang, *body])
        if path.endswith("/"):
            new_path += "/"
    return urlunsplit((sp.scheme, sp.netloc, new_path, sp.query, sp.fragment))


def _delocalize_link(url: str) -> str:
    """Strip a leading language subfolder, returning the canonical (root) URL:
    ``site.com/es/foo`` → ``site.com/foo``; ``site.com/es/`` → ``site.com/``.
    A URL with no leading language is returned unchanged."""
    sp = urlsplit(url if _SCHEME_RE.match(url) else "https://" + url if _host_of(url) else url)
    if not sp.netloc:
        return url
    path = sp.path or ""
    segs = [s for s in path.split("/") if s != ""]
    if not (segs and _is_lang_seg(segs[0])):
        return url
    body = segs[1:]
    if not body:
        new_path = "/"
    else:
        new_path = "/" + "/".join(body)
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


def _exc_cands(url: str) -> set[str]:
    """Comparable keys for an original link, used to match it against an
    exception ``page``. Built from BOTH the link as-is and its de-localized
    form, so an exception listed canonically (``dexsport.io/``,
    ``dexsport.io/sports/...``) still matches a source link that carries a
    language subfolder (``dexsport.io/es/``, ``dexsport.io/es/sports/...``)."""
    cands: set[str] = set()
    for u in {url, _delocalize_link(url)}:
        host = _host_of(u)
        sp = urlsplit(u if _SCHEME_RE.match(u) else "https://" + u if host else u)
        path = (sp.path or "").strip("/").lower()
        cands.add(_exc_key(u))  # host/path
        if path:
            cands.add(path)  # products/x
            cands.add(path.split("/")[-1])  # slug
            if host:
                cands.add(f"{host}/{path}")
        elif host:
            cands.add(host)  # bare homepage
    return cands


def exception_matches(url: str, lang: str, exceptions: list[dict]) -> bool:
    """True if (lang, page) lists this link. ``page`` may be a full URL, a
    path, or just the slug — matched permissively against all three forms, and
    against the link's de-localized form so a source-language subfolder doesn't
    defeat a canonically-listed exception."""
    lang = lang.strip().lower()
    cands = _exc_cands(url)
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
    default_langs: dict[str, str] | None = None,
) -> str:
    """The link ``url`` SHOULD become in the translation for ``lang``."""
    if link_type == "product":
        if exception_matches(url, lang, exceptions):
            # Exception page is NOT localized — it keeps the canonical root URL
            # (drop any source-language subfolder so it isn't expected to carry
            # the original language, e.g. ``dexsport.io/es/`` → ``dexsport.io/``).
            return _delocalize_link(url)
        # A product site that serves the target language at its root gets no
        # subfolder (default-language convention).
        dl = default_lang_for(_host_of(url), default_langs or {})
        return localize_link(url, lang, default_lang=dl)
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
    default_langs: dict[str, str] | None = None,
) -> list[str]:
    """Expected (localized) links for one row's original content.

    ``internal_domains`` are per-row (read from the chosen domain columns);
    ``product_domains`` are the global product domain(s). ``default_langs`` maps
    a product domain to the language it serves at its root (no subfolder).
    Returns absolute, scheme-bearing URLs (deduped, order-preserving) so the
    materialized expected column parses under the checker's expected-link
    extractor and juxtaposes cleanly against the translation."""
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
            default_langs=default_langs,
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


def _strip_all_www(nlink: str) -> str:
    """Collapse any repeated leading ``www.`` on a normalized link's host.

    ``normalize_link`` already drops ONE ``www.``; a translation can carry a
    doubled prefix (``www.www.fifa.com`` → after normalize → ``www.fifa.com``).
    Stripping the rest lets the matcher recognize it as a wrong version of the
    original FIFA link (a discrepancy) rather than a made-up one."""
    while nlink.startswith("www."):
        nlink = nlink[4:]
    return nlink


def _host_key(nlink: str) -> str:
    """The comparable host of a normalized link: the part before the first
    ``/``, with any leading ``www.`` collapsed. Two links share a domain iff
    their host keys are equal (mirrors the frontend's ``hostOf``)."""
    return _strip_all_www(nlink.split("/", 1)[0])


def _common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def _path_segments(nlink: str) -> list[str]:
    """Path segments of a normalized link (host dropped), with a leading
    language subfolder removed so a localized link lines up with its original
    (``host/es/formazioni/spagna`` → ``["formazioni", "spagna"]``)."""
    segs = nlink.split("/")[1:]
    if segs and _is_lang_seg(segs[0]):
        segs = segs[1:]
    return segs


def _suffix_seg_overlap(a: list[str], b: list[str]) -> int:
    """How many trailing path segments two links share (aligned from the end).
    The slug usually carries the identity (``spagna`` vs ``francia``), so this
    discriminates same-host originals far better than a raw character prefix —
    which ties at the host when the very first path segment differs."""
    n = 0
    i, j = len(a) - 1, len(b) - 1
    while i >= 0 and j >= 0 and a[i] == b[j]:
        n += 1
        i -= 1
        j -= 1
    return n


def strip_link_in_text(text: str, url: str) -> tuple[str, int]:
    """Remove the link ``url`` but KEEP its anchor text — for a link that
    shouldn't be there at all. ``<a … href="url" …>anchor</a>`` → ``anchor``;
    a markdown ``[anchor](url)`` → ``anchor``. Returns ``(new_text, count)``.
    The href must match in full (closing quote right after ``url``), so a longer
    URL sharing the prefix is left alone."""
    if not text or not url:
        return text, 0
    u = re.escape(url)
    count = 0
    anchor_re = re.compile(
        r"<a\b[^>]*?href\s*=\s*[\"']" + u + r"[\"'][^>]*>(.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    text, n1 = anchor_re.subn(lambda m: m.group(1), text)
    count += n1
    md_re = re.compile(r"\[([^\]]*)\]\(\s*" + u + r"\s*\)")
    text, n2 = md_re.subn(lambda m: m.group(1), text)
    count += n2
    return text, count


def replace_link_in_text(text: str, old: str, new: str) -> tuple[str, int]:
    """Swap the link ``old`` for ``new`` wherever it appears in ``text`` as a
    COMPLETE link — i.e. not as a prefix of a longer URL (so replacing
    ``site.com/a`` never mangles ``site.com/a/b``). Matches the href/markdown
    forms the extractor finds. Returns ``(new_text, count)``."""
    if not text or not old or old == new:
        return text, 0
    # The negative lookahead asserts the char after ``old`` isn't a URL-path
    # continuation, so only a whole link (followed by a quote, ``)``, ``<``,
    # whitespace, or end) is replaced.
    pattern = re.escape(old) + r"(?![A-Za-z0-9/_\-.?=&%#])"
    return re.subn(pattern, lambda _m: new, text)


def _pair_weight(nt: str, o: str) -> int:
    """Similarity of a translation link to an original (both normalized): shared
    trailing path segments dominate; the character prefix breaks ties.

    Returns -1 for an INELIGIBLE pair — one with no real signal: a different
    content page (no shared slug) on the same domain. Such a pair is never
    assigned, so a wrong link is left "no good match" rather than forced onto an
    unrelated page. A homepage original (no path) stays eligible, since a link
    that matches nothing else plausibly "should be" the localized root."""
    suffix = _suffix_seg_overlap(_path_segments(nt), _path_segments(o))
    if suffix == 0 and len(_path_segments(o)) > 0:
        return -1
    return suffix * 1000 + _common_prefix_len(nt, o)


def assign_links(links: list[str], pool: list[str]) -> dict[str, str | None]:
    """Optimal one-to-one assignment of same-domain "wrong" links to candidate
    originals, maximizing total similarity. Each original is used at most once;
    a link left without an original maps to None ("no good match") instead of
    being forced onto another link's expected.

    Exact via a bitmask DP for the small sets a row produces; a greedy
    highest-weight-first pass guards the rare large case so it can't blow up."""
    if not links:
        return {}
    if not pool:
        return {ln: None for ln in links}
    weights = [[_pair_weight(ln, o) for o in pool] for ln in links]
    k, m = len(links), len(pool)

    if m <= 12 and k <= 20:
        @lru_cache(maxsize=None)
        def solve(i: int, used: int) -> tuple[int, tuple[int, ...]]:
            if i == k:
                return (0, ())
            # Leaving link i unassigned (a "no good match" leftover).
            skip_score, skip_choice = solve(i + 1, used)
            best = (skip_score, (-1,) + skip_choice)
            for j in range(m):
                if used & (1 << j) or weights[i][j] < 0:  # taken or ineligible
                    continue
                sub_score, sub_choice = solve(i + 1, used | (1 << j))
                score = weights[i][j] + sub_score
                if score > best[0]:
                    best = (score, (j,) + sub_choice)
            return best

        choices = solve(0, 0)[1]
        solve.cache_clear()
    else:
        order = sorted(
            (
                (weights[i][j], i, j)
                for i in range(k)
                for j in range(m)
                if weights[i][j] >= 0
            ),
            reverse=True,
        )
        chosen = [-1] * k
        used_o: set[int] = set()
        for _w, i, j in order:
            if chosen[i] == -1 and j not in used_o:
                chosen[i] = j
                used_o.add(j)
        choices = tuple(chosen)

    return {
        links[i]: (pool[choices[i]] if choices[i] >= 0 else None)
        for i in range(k)
    }


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
    default_langs: dict[str, str] | None = None,
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
    seen_o_norm: set[str] = set()
    pairs: list[tuple[str, str, str]] = []  # (original_norm, expected_url, type)
    origurl_by_norm: dict[str, str] = {}  # original_norm → its absolute URL
    for raw in extract_output_links(original_text):
        absu = _ensure_scheme(raw, default_host)
        o_norm = normalize_link(absu)
        # Dedup originals by NORMALIZED form so a link repeated in the content
        # — or written with a trailing slash / www / fragment variation — is
        # processed once instead of producing redundant pairs.
        if o_norm in seen_o_norm:
            continue
        seen_o_norm.add(o_norm)
        original.append(absu)
        origurl_by_norm[o_norm] = absu
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
            default_langs=default_langs,
        )
        pairs.append((o_norm, e, ltype))

    expected_norm = {normalize_link(e) for (_o, e, _t) in pairs}

    # Dedup translation links by normalized form too: a link repeated in the
    # translated content is one logical link to check, so it shouldn't show as
    # two rows or count its error twice. First raw occurrence is kept.
    translation: list[str] = []
    seen_t_norm: set[str] = set()
    for t in extract_output_links(translated_text):
        nt = normalize_link(t)
        if nt in seen_t_norm:
            continue
        seen_t_norm.add(nt)
        translation.append(t)

    # Index originals for matching. ``orig_keys`` powers precise pairing (exact
    # match, a dropped language segment, or a collapsed www); ``orig_by_host``
    # powers the domain-level rule below. ``exp_by_orig`` maps each original
    # norm to the link it SHOULD have become.
    orig_keys: dict[str, str] = {}
    orig_by_host: dict[str, list[str]] = {}
    exp_by_orig: dict[str, str] = {}
    for (o, e, _t) in pairs:
        orig_keys.setdefault(o, o)
        orig_keys.setdefault(_strip_all_www(o), o)
        orig_by_host.setdefault(_host_key(o), []).append(o)
        exp_by_orig.setdefault(o, e)

    # An original is "covered" when its expected link already appears verbatim
    # among the translation links — i.e. some link already got it right. The
    # fallback below avoids re-pairing a different discrepancy onto a covered
    # original, so one expected isn't claimed twice (once correctly, once as a
    # wrong guess). This is what stops a mistranslated homepage from latching
    # onto a ``/top/underdogs/`` original that another link already matched.
    trans_norm = {normalize_link(t) for t in translation}
    covered_origs = {
        o for (o, e, _t) in pairs if normalize_link(e) in trans_norm
    }

    def _precise(nt: str) -> str | None:
        """A CONFIDENT match for a wrong link: exact, a dropped language
        segment, or a collapsed www. (Wrong-language duplicates may legitimately
        share one original, so precise matches aren't mutually exclusive.) The
        ambiguous same-domain links are resolved by the assignment below."""
        loose = _strip_all_www(nt)
        for key in (nt, _strip_first_seg(nt), loose, _strip_first_seg(loose)):
            o = orig_keys.get(key)
            if o is not None:
                return o
        return None

    # Pass 1: tag each translation link. ``ok`` matches an expected; a confident
    # match becomes a discrepancy stamped with its original/expected; the rest of
    # the same-domain links are deferred to the per-domain assignment; anything
    # on no known domain is ``invented``.
    tagged_trans: list[dict] = []
    precise_claimed: set[str] = set()
    fallback: dict[str, list[tuple[dict, str]]] = {}  # host → [(tag, nt), …]
    for t in translation:
        nt = normalize_link(t)
        # Carry each translation link's type so the raw-table column can label
        # it without re-deriving from the (now-folded) aligned grid.
        ltype = classify_link(t, internal_domains, product_domains)
        if nt in expected_norm:
            tagged_trans.append({"url": t, "kind": "ok", "link_type": ltype})
            continue
        tag: dict = {"url": t, "kind": "discrepancy", "link_type": ltype}
        tagged_trans.append(tag)
        o = _precise(nt)
        if o is not None:
            tag["expected"] = exp_by_orig.get(o)
            tag["original"] = origurl_by_norm.get(o)
            precise_claimed.add(o)
        elif _host_key(nt) in orig_by_host:
            fallback.setdefault(_host_key(nt), []).append((tag, nt))
        else:
            tag["kind"] = "invented"

    # Pass 2: globally assign the ambiguous same-domain links to the leftover
    # originals (uncovered by an ok link and not already taken by a precise
    # match), maximizing total similarity so each original is used once. A link
    # with no original left keeps no ``expected`` — an honest "no good match"
    # rather than being forced onto a wrong one.
    for host, items in fallback.items():
        pool = [
            o
            for o in orig_by_host[host]
            if o not in covered_origs and o not in precise_claimed
        ]
        assignment = assign_links([nt for (_tag, nt) in items], pool)
        for (tag, nt) in items:
            o = assignment.get(nt)
            if o is not None:
                tag["expected"] = exp_by_orig.get(o)
                tag["original"] = origurl_by_norm.get(o)

    # ``aligned`` is one entry per WRONG translation link (discrepancy or
    # invented) — it drives the endpoint's view/link-type filtering and error
    # counts. Omitted expected links (present in neither side) aren't surfaced
    # in the folded translation-column UI, so they no longer get an entry.
    aligned: list[dict] = []
    for tag in tagged_trans:
        if tag["kind"] == "ok":
            continue
        aligned.append(
            {
                "expected": tag.get("expected"),
                "wrong": tag,
                "link_type": tag["link_type"],
            }
        )

    return {
        "original": original,
        "translation": tagged_trans,
        "aligned": aligned,
    }
