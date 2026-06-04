"""The AI half of the Google-Docs → Custom-CMS importer.

Two jobs the deterministic cleanup (services/gdocs_clean) can't do well:

1. **Pairing** — a sheet row lists its pages in a "Structure" cell and links
   each page to a Google Doc, but the page wording in Structure and the Doc's
   title / link anchor often differ ("About us" vs "About — Acme", "shop" vs
   "Our Store"). We pair each Structure page to a Doc: an exact normalized
   match first (free), then one small LLM call for whatever is left.

2. **Meta** — each Doc starts with a meta title + meta description (labelled,
   e.g. "Meta Title: …" / "Description: …"). We read them deterministically
   when the labels are clear, and fall back to one LLM call on the head of the
   Doc when they aren't. Either way the meta block is stripped from the body so
   it doesn't end up duplicated in the published content.

Provider/model are resolved once by the caller (the import task) and passed in,
so this module never touches settings — it just runs prompts and parses JSON
defensively.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from app.providers.base import BaseProvider, GenerationParams
from app.services.gdocs_clean import html_to_text

# ----------------------------------------------------------------------------
# Normalization + JSON parsing helpers
# ----------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize(s: str | None) -> str:
    """Lowercase, drop punctuation, collapse whitespace — for fuzzy equality."""
    if not s:
        return ""
    s = _PUNCT.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


def _parse_json(text: str):
    """Parse a JSON object/array out of an LLM response, tolerating code
    fences and surrounding prose. Returns the parsed value or None."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        # drop the opening fence line and the trailing fence
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # Last resort: grab the outermost {...} or [...] span.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = t.find(open_c), t.rfind(close_c)
        if 0 <= i < j:
            try:
                return json.loads(t[i : j + 1])
            except json.JSONDecodeError:
                continue
    return None


# ----------------------------------------------------------------------------
# Pairing: Google Docs  ->  Structure entries (the slug source of truth)
# ----------------------------------------------------------------------------
#
# The Structure column is authoritative for slugs; the Links-column anchors are
# unreliable (writers fat-finger them — sometimes a page name, sometimes a full
# path, sometimes a raw Doc URL). So we DON'T trust the anchor as a slug; we use
# the LLM to map each Doc to the Structure entry it actually represents, reading
# the Doc's title + content (the anchor is given only as a weak hint). The slug
# is then taken from that Structure entry. Docs the model can't place stay
# imported but get the NO_EXACT_SLUG placeholder.


@dataclass
class DocToPair:
    """One Doc to place against the site's Structure."""

    doc_id: str
    anchor: str = ""  # the writer's link anchor — the primary matching signal
    title: str = ""   # the doc's SEO title — a secondary hint


PAIR_STRUCT_SYSTEM_PROMPT = (
    "You map each article to the website page it belongs to, for ONE site. You "
    "are given STRUCTURE — the authoritative, indexed list of that site's pages "
    "— and DOCS, each with an index, the writer's link ANCHOR, and the doc's SEO "
    "title. The ANCHOR is the primary signal — it names the page the writer "
    "intended (it may be a page name like 'France' or a path like "
    "'/teams/france-world-cup-winner/'); use the SEO title only as a secondary "
    "hint. Match each doc to the structure page its anchor points to. Each "
    "structure page maps to at most one doc. If a doc matches no page, use null. "
    "Respond with ONLY a JSON object mapping each doc index (as a string) to a "
    'structure index (integer) or null, e.g. {"0":2,"1":null}. No prose, no '
    "code fences."
)


def _clean_inline(text: str, limit: int) -> str:
    """Collapse to a single trimmed line so the prompt list stays readable."""
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


async def pair_docs_to_structure(
    provider: BaseProvider,
    model: str,
    *,
    structure: list[str],
    docs: list[DocToPair],
    system_prompt: str | None = None,
) -> dict[str, int | None]:
    """Map each Doc to a Structure index (or None) from its SEO title. One LLM
    call per site.

    Docs are keyed to the model by a small ordinal index (NOT the 44-char Google
    Doc id — models can't reliably echo those back), then mapped to doc_ids on
    return. ``structure`` is the candidate page list (already filtered to real
    pages by the caller). Each structure index is used at most once.
    ``system_prompt`` overrides the built-in prompt (Brain ``gdocs_pairing``).
    """
    if not docs:
        return {}
    out: dict[str, int | None] = {d.doc_id: None for d in docs}
    if not structure:
        return out

    struct_lines = "\n".join(f"{i}: {s}" for i, s in enumerate(structure))
    doc_lines = "\n".join(
        f'{n}: anchor="{_clean_inline(d.anchor, 120)}" | '
        f'seo="{_clean_inline(d.title, 120)}"'
        for n, d in enumerate(docs)
    )
    user = (
        f"STRUCTURE (index: page):\n{struct_lines}\n\n"
        f"DOCS (index: anchor | seo):\n{doc_lines}"
    )
    # Retry transient failures (rate-limit / timeout). Without this, a single
    # 429 dropped a whole site's docs to NO_EXACT_SLUG.
    parsed = None
    for attempt in range(3):
        try:
            result = await provider.generate(
                prompt=user,
                model=model,
                params=GenerationParams(
                    temperature=0.0,
                    max_output_tokens=1024,
                    system=system_prompt or PAIR_STRUCT_SYSTEM_PROMPT,
                ),
            )
            parsed = _parse_json(result.text)
            break
        except Exception:
            if attempt == 2:
                return out  # give up — caller flags these as NO_EXACT_SLUG
            await asyncio.sleep(1.5 * (attempt + 1))

    if isinstance(parsed, dict):
        used: set[int] = set()
        for k, v in parsed.items():
            try:
                doc_idx = int(k)
            except (ValueError, TypeError):
                continue
            if not (0 <= doc_idx < len(docs)):
                continue
            if isinstance(v, bool) or not isinstance(v, int):
                continue
            if 0 <= v < len(structure) and v not in used:
                out[docs[doc_idx].doc_id] = v
                used.add(v)
    return out


# ----------------------------------------------------------------------------
# Meta: extract seo_title + seo_description, strip the meta block from the body
# ----------------------------------------------------------------------------


@dataclass
class MetaResult:
    seo_title: str = ""
    seo_description: str = ""
    body_html: str = ""
    method: str = "none"  # 'deterministic' | 'ai' | 'partial' | 'none'
    warnings: list[str] = field(default_factory=list)


# Leading block (paragraph / heading) regex — cleaned HTML has no nesting.
_LEAD_BLOCK = re.compile(r"<(p|h[1-6])(?:\s[^>]*)?>(.*?)</\1>", re.IGNORECASE | re.DOTALL)

# Optional qualifier that may precede the label word (Meta / SEO in EN, and
# their Cyrillic spellings). IGNORECASE + str patterns fold Unicode case, so
# "СЕО"/"Мета" match too. Kept self-contained (whole group optional) so the
# label may also appear bare ("Title:", "Заголовок:").
_QUAL = r"(?:(?:meta|seo|сео|мета)\b[\s\-]*)?"

_TITLE_LABEL = re.compile(
    r"^\s*" + _QUAL + r"(?:title|тайтл|заголовок)\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)
_DESC_LABEL = re.compile(
    r"^\s*" + _QUAL + r"(?:description|desc|описание|опис|дескрипшн)\s*[:\-–—]\s*(.+)$",
    re.IGNORECASE,
)

# How many leading blocks we are willing to treat as the meta region.
_MAX_LEAD = 8

# A <br> inside a leading block. Google often exports the meta title + meta
# description as ONE paragraph split by <br> ("Meta Title: …<br>Meta
# Description: …"), so we split a block on <br> and match each visual line.
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


def extract_meta_deterministic(
    body_html: str,
) -> tuple[str, str, list[tuple[str, str]]]:
    """Find labelled meta title/description in the first few blocks.

    Each leading block is split on ``<br>`` so a combined "Meta Title: …<br>
    Meta Description: …" paragraph is handled (the run-15 case). Returns
    ``(title, desc, replacements)`` where ``replacements`` is a list of
    ``(old_block, new_block)`` edits to apply to the body: a meta-only block
    maps to ``""`` (removed); a block that mixed meta lines with real content
    is rebuilt without the meta lines. Empty strings when a label isn't found.
    """
    title = ""
    desc = ""
    replacements: list[tuple[str, str]] = []
    for n, m in enumerate(_LEAD_BLOCK.finditer(body_html)):
        if n >= _MAX_LEAD:
            break
        tag = m.group(1)
        segments = _BR.split(m.group(2))
        kept: list[str] = []
        block_had_meta = False
        for seg in segments:
            seg_text = html_to_text(seg).strip()
            if not seg_text:
                continue
            mt = _TITLE_LABEL.match(seg_text)
            md = _DESC_LABEL.match(seg_text)
            if mt and not title:
                title = mt.group(1).strip()
                block_had_meta = True
            elif md and not desc:
                desc = md.group(1).strip()
                block_had_meta = True
            else:
                kept.append(seg.strip())
        if block_had_meta:
            new_inner = "<br>".join(s for s in kept if s)
            new_block = f"<{tag}>{new_inner}</{tag}>" if new_inner else ""
            replacements.append((m.group(0), new_block))
        elif title or desc:
            # First non-meta block after we've captured meta → body starts here.
            break
    return title, desc, replacements


def _apply_replacements(body_html: str, replacements: list[tuple[str, str]]) -> str:
    out = body_html
    for old, new in replacements:
        out = out.replace(old, new, 1)
    return out.strip()


def _strip_blocks(body_html: str, blocks: set[str]) -> str:
    out = body_html
    for b in blocks:
        out = out.replace(b, "", 1)
    return out.strip()


# A leading "Label: value" shape — a short prefix (≤30 chars, no colon) then a
# colon then the value. Used to recognise a meta line whose exact label wording
# we didn't match deterministically (e.g. a localized label) so we can strip it.
_LABEL_PREFIX = re.compile(r"^[^:]{1,30}:\s*(.+)$", re.DOTALL)


def _strip_value_blocks(body_html: str, *values: str) -> str:
    """Remove leading *labelled* blocks whose value equals an AI-supplied meta
    value.

    Only blocks shaped like ``Label: <value>`` are eligible — a bare body
    paragraph the model merely summarised or echoed is never stripped, so an
    unlabelled article never loses its opening text. This is the fallback for
    meta lines whose label wording :func:`extract_meta_deterministic` missed."""
    targets = [normalize(v) for v in values if v and len(normalize(v)) >= 4]
    if not targets:
        return body_html
    to_strip: set[str] = set()
    for n, m in enumerate(_LEAD_BLOCK.finditer(body_html)):
        if n >= _MAX_LEAD:
            break
        text = html_to_text(m.group(2)).strip()
        pm = _LABEL_PREFIX.match(text)
        if not pm:
            continue
        value_part = normalize(pm.group(1))
        if not value_part:
            continue
        if any(
            t == value_part or (t in value_part and len(value_part) - len(t) < 12)
            for t in targets
        ):
            to_strip.add(m.group(0))
    return _strip_blocks(body_html, to_strip)


META_SYSTEM_PROMPT = (
    "You extract SEO metadata from the top of an article. The article begins "
    "with a meta/SEO title and a meta description (the labels may vary or be "
    "absent). Return ONLY a JSON object with keys \"seo_title\" and "
    "\"seo_description\" containing the plain-text values (no labels, no "
    "quotes, no HTML). If a value is genuinely absent, use an empty string. No "
    "prose, no code fences."
)


async def extract_meta(
    provider: BaseProvider,
    model: str,
    *,
    doc_title: str,
    body_html: str,
    system_prompt: str | None = None,
) -> MetaResult:
    """Pull seo_title + seo_description and return the body with the meta block
    removed. Deterministic when the labels are clear; one LLM call otherwise.

    ``system_prompt`` overrides the built-in meta prompt (the import task passes
    the admin-editable Brain ``gdocs_meta`` prompt); falls back to the default."""
    res = MetaResult(body_html=body_html)
    det_title, det_desc, replacements = extract_meta_deterministic(body_html)

    if det_title and det_desc:
        res.seo_title = det_title
        res.seo_description = det_desc
        res.body_html = _apply_replacements(body_html, replacements)
        res.method = "deterministic"
        return res

    # AI fallback on the head of the doc (keep the prompt small).
    head_text = html_to_text(body_html)[:2500]
    parsed = None
    try:
        result = await provider.generate(
            prompt=f"ARTICLE TITLE: {doc_title}\n\nARTICLE START:\n{head_text}",
            model=model,
            params=GenerationParams(
                temperature=0.0,
                max_output_tokens=512,
                system=system_prompt or META_SYSTEM_PROMPT,
            ),
        )
        parsed = _parse_json(result.text)
    except Exception as exc:  # provider failure shouldn't kill the whole import
        res.warnings.append(f"meta AI call failed: {exc}")

    ai_title = ai_desc = ""
    if isinstance(parsed, dict):
        ai_title = str(parsed.get("seo_title") or "").strip()
        ai_desc = str(parsed.get("seo_description") or "").strip()

    res.seo_title = det_title or ai_title
    res.seo_description = det_desc or ai_desc

    # Strip whatever we can anchor: labelled blocks (det) + value-matched blocks.
    body = _apply_replacements(body_html, replacements)
    body = _strip_value_blocks(body, res.seo_title, res.seo_description)
    res.body_html = body

    if res.seo_title and res.seo_description:
        res.method = "ai" if not (det_title and det_desc) else "deterministic"
    elif res.seo_title or res.seo_description:
        res.method = "partial"
    else:
        res.method = "none"
        res.warnings.append("no meta title/description found")
    return res
