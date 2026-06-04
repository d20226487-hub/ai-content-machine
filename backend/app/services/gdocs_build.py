"""Pure helpers for assembling the imported bulk table.

The Celery task (tasks/gdocs_import) does the DB writes; this module holds the
deterministic, unit-testable decisions: how to slugify a page name, whether a
run is single- or multi-site, and the column layout (which mirrors the
Custom-CMS publishing fields so the resulting table is publish-ready).
"""
from __future__ import annotations

import re
import unicodedata

# Cyrillic → Latin transliteration so Russian/Ukrainian page names yield usable
# slugs instead of collapsing to empty. Covers RU + the UA-specific letters.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e",
    "ё": "e", "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "iu", "я": "ia",
}

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def is_slug(value: str) -> bool:
    """True when ``value`` is already a clean lowercase hyphen slug."""
    return bool(value) and bool(_SLUG_RE.match(value.strip()))


def is_page_entry(value: str) -> bool:
    """True for a Structure line that's a real, publishable page.

    Drops bracketed annotation lines the writers leave in the Structure column —
    e.g. ``"Teams (pillar page, not as a separate page)"`` — which are notes, not
    pages. Used so the stored site structure, the planned-pages count, and the
    AI pairing candidates all ignore them."""
    s = (value or "").strip()
    return bool(s) and "(" not in s and ")" not in s


def _transliterate(text: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in text)


def _fold_latin(text: str) -> str:
    """Drop diacritics from accented Latin letters (é→e, ñ→n, ç→c, ã→a …).

    Decomposes with NFKD and removes the combining marks. Essential for the
    FR/ES/PT page names this importer sees — without it ``Brésil`` slugged to
    ``br-sil`` and ``España`` to ``espa-a``. Cyrillic is handled separately by
    ``_transliterate`` (run first), so this only touches Latin accents."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def slugify(value: str, *, fallback: str = "") -> str:
    """Slugify a page name, keeping it if it already is a slug.

    Lowercases, transliterates Cyrillic, folds Latin diacritics, replaces any
    run of non ``[a-z0-9]`` with a single hyphen, and trims hyphens. Returns
    ``fallback`` when nothing usable remains (e.g. an all-symbol name)."""
    if not value:
        return fallback
    v = value.strip()
    if is_slug(v):
        return v
    v = _fold_latin(_transliterate(v.lower()))
    v = _NON_SLUG.sub("-", v).strip("-")
    return v or fallback


# Anchor texts that mean "the home page" → slug "home". Covers the bare path,
# common English spellings, and a couple of localized variants. Compared after
# lowercasing + trimming surrounding slashes/spaces.
_HOME_TOKENS = {
    "",
    "home",
    "homepage",
    "home page",
    "index",
    "main",
    "главная",
    "главная страница",
    "accueil",
    "inicio",
}


def slug_from_link(value: str, *, fallback: str = "") -> str:
    """Derive a slug from a link's anchor text (the new slug source).

    The anchor may be a URL path (``/stadiums/canada/bmo-field/``) or a human
    page name (``Host cities``) — we handle both:

    * home variants (``/``, ``home``, ``homepage``, ``index`` …) → ``"home"``
    * a path (contains ``/``) → each segment slugified, rejoined with ``/`` so
      nested pages keep their hierarchy (``stadiums/canada/bmo-field``); a bare
      scheme+host that slipped in is dropped first
    * otherwise a plain name → :func:`slugify`
    """
    raw = (value or "").strip()
    if raw.strip().strip("/").strip().lower() in _HOME_TOKENS:
        return "home"
    if "/" in raw:
        # Drop a scheme+host if a full URL was used as the anchor.
        path = re.sub(r"^[a-z][a-z0-9+.\-]*://[^/]+", "", raw, flags=re.IGNORECASE)
        segs = [slugify(seg) for seg in path.split("/")]
        segs = [s for s in segs if s]
        return "/".join(segs) if segs else "home"
    return slugify(raw, fallback=fallback)


# Placeholder slug for a Doc whose link anchor yields no usable slug (e.g. the
# anchor is a raw Doc URL). The Doc is still imported, just flagged for a human.
NO_EXACT_SLUG = "no-exact-slug"

_NORM_WS = re.compile(r"\s+")
_NORM_PUNCT = re.compile(r"[^0-9a-zЀ-ӿ]+")  # keep latin + cyrillic
# An anchor that is itself a raw Google-Doc URL — has no human-readable slug, so
# we fall back to NO_EXACT_SLUG rather than slugifying the URL into junk.
_DOC_URL = re.compile(r"docs\.google\.com/document|/document/d/", re.IGNORECASE)


def _norm_label(value: str) -> str:
    """Loose normalization for matching an anchor to a Structure entry —
    lowercase, drop punctuation, collapse whitespace."""
    if not value:
        return ""
    v = _NORM_PUNCT.sub(" ", value.strip().lower())
    return _NORM_WS.sub(" ", v).strip()


def pair_slug(label: str, structure: list[str]) -> tuple[str, str]:
    """Resolve a link's slug from its anchor text. Returns ``(slug, status)``:

    * ``"matched"`` — the anchor corresponds to a Structure entry; that entry's
      slug is used (the Structure value is authoritative).
    * ``"anchor"`` — no Structure match, but the anchor is itself a usable slug
      (a URL path like ``/teams/france-world-cup-winner/`` or a page name); we
      slugify the anchor directly. Sites vary: some link by name, some by path —
      both are good slugs, so we keep them rather than discard them.
    * ``"unresolved"`` — the anchor is a raw Doc URL (no human slug) → the Doc is
      still imported with ``NO_EXACT_SLUG`` and flagged for a human.
    """
    anchor_slug = slug_from_link(label)
    anchor_norm = _norm_label(label)
    for entry in structure:
        if not entry:
            continue
        if slug_from_link(entry) == anchor_slug or _norm_label(entry) == anchor_norm:
            return slug_from_link(entry), "matched"
    if _DOC_URL.search(label or ""):
        return NO_EXACT_SLUG, "unresolved"
    if anchor_slug and anchor_slug != NO_EXACT_SLUG:
        return anchor_slug, "anchor"
    return NO_EXACT_SLUG, "unresolved"


def normalize_domain(value: str) -> str:
    """Lowercase + strip a domain cell so distinct-count is stable.

    Drops a scheme and any path so ``https://Example.com/`` and
    ``example.com`` count as the same site."""
    if not value:
        return ""
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/", 1)[0]
    return v.strip()


def decide_mode(domains: list[str]) -> str:
    """'multi' when more than one distinct non-empty domain appears, else
    'single'. Empty list → 'single' (degenerate but harmless)."""
    distinct = {normalize_domain(d) for d in domains if normalize_domain(d)}
    return "multi" if len(distinct) > 1 else "single"


# Column layout, in order. Each entry is (column_name, custom_cms_field_key).
# ``field_key`` documents how the column maps onto the Custom-CMS publish
# fields (lang/slug/title/content/seo_title/seo_description/id); the Domain
# column is the per-row site source in multi mode. id/post_url are left empty
# for parity with hand-built tables (filled after the first publish).
_BASE_LAYOUT: list[tuple[str, str | None]] = [
    ("Language", "lang"),
    ("Slug", "slug"),
    ("Title", "title"),
    ("Content", "content"),
    ("SEO Title", "seo_title"),
    ("SEO Description", "seo_description"),
    ("Post ID", "id"),
    ("Post URL", None),
]


def column_layout(mode: str) -> list[tuple[str, str | None]]:
    """Ordered (name, field_key) columns for the given mode. Multi prepends a
    Domain column used as the per-row site source."""
    if mode == "multi":
        return [("Domain", "domain")] + _BASE_LAYOUT
    return list(_BASE_LAYOUT)
