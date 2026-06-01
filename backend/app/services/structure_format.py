"""Structure & Formatting transforms for bulk-table cells.

Four deterministic, user-selectable transforms run on output cells. They
ALWAYS run in a fixed order (markdown -> response_start -> inline_css ->
html_format) because later steps assume earlier ones already ran — e.g.
``markdown`` emits ``<strong>`` that ``html_format`` may then unwrap. The
user picks a SUBSET; whatever is picked runs in this canonical order.

Surgical regex on purpose (no HTML parser): each transform only touches the
exact tokens it targets, so the before/after diff stays clean. A full parse +
re-serialize would rewrite untouched markup and create diff noise.

  1. markdown        — convert stray markdown to HTML (headings, bold, italic,
                       links, lists, inline code, blockquotes); existing HTML
                       is left alone.
  2. response_start  — strip leading junk so the cell starts at a real tag:
                       a ```html / ``` fence, a bare leading "html" word, a
                       <!DOCTYPE>, and the <html>/<head>/<body> document
                       wrapper (keep the body's inner content).
  3. inline_css      — drop ``style="…"`` attributes and ``<style>`` blocks,
                       leaving other attributes (href, src, …) intact.
  4. html_format     — unwrap <b> <strong> <i> <em> <u>, keeping inner text.
"""
from __future__ import annotations

import re

# Canonical order. Selection is a subset, always applied in THIS order.
OPERATIONS: tuple[str, ...] = (
    "markdown",
    "response_start",
    "inline_css",
    "html_format",
)


# ---------- 1. markdown -> HTML ----------

_MD_LINK = re.compile(r"\[([^\]]+)\]\(\s*([^)\s]+)\s*\)")
# **bold** / __bold__ — no space just inside the delimiters.
_MD_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
# *italic* / _italic_ — single delimiter, not part of a ** pair.
_MD_ITALIC = re.compile(r"(?<![*_\w])([*_])(?=\S)([^*_]+?)(?<=\S)\1(?![*_\w])")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_MD_ULI = re.compile(r"^[ \t]*[-*+]\s+(.+)$")
_MD_OLI = re.compile(r"^[ \t]*\d+\.\s+(.+)$")


def _md_inline(text: str) -> str:
    text = _MD_LINK.sub(
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text
    )
    text = _MD_BOLD.sub(lambda m: f"<strong>{m.group(2)}</strong>", text)
    text = _MD_ITALIC.sub(lambda m: f"<em>{m.group(2)}</em>", text)
    text = _MD_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    return text


def markdown_to_html(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    list_type: str | None = None  # 'ul' | 'ol' | None

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            out.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        h = _MD_HEADING.match(line)
        uli = _MD_ULI.match(line)
        oli = _MD_OLI.match(line)
        bq = _MD_BLOCKQUOTE.match(line)
        if h:
            close_list()
            level = len(h.group(1))
            out.append(f"<h{level}>{_md_inline(h.group(2))}</h{level}>")
        elif uli or oli:
            want = "ul" if uli else "ol"
            if list_type and list_type != want:
                close_list()
            if not list_type:
                list_type = want
                out.append(f"<{want}>")
            item = (uli or oli).group(1)  # type: ignore[union-attr]
            out.append(f"<li>{_md_inline(item)}</li>")
        elif bq:
            close_list()
            out.append(f"<blockquote>{_md_inline(bq.group(1))}</blockquote>")
        else:
            close_list()
            out.append(_md_inline(line))
    close_list()
    return "\n".join(out)


# ---------- 2. response_start ----------

_FENCE_START = re.compile(r"^\s*`{3,}[a-zA-Z0-9]*[ \t]*\r?\n?")
_FENCE_END = re.compile(r"\r?\n?[ \t]*`{3,}\s*$")
# A bare leading "html" the model sometimes emits before the real content.
_LEADING_HTML_WORD = re.compile(r"^\s*html\b[ \t]*\r?\n?", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)
_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)
_HEAD_BLOCK = re.compile(r"<head[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)
# Any leftover document-scaffolding tag — opening OR closing. The lookahead
# pins the tag name so content tags like <header>, <hr>, <h1>, <a> are never
# matched.
_SCAFFOLD_TAGS = re.compile(
    r"</?(?:html|body|head|title|meta|link|base)(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)


def strip_response_start(text: str) -> str:
    if not text:
        return text
    s = text
    s = _FENCE_START.sub("", s)
    s = _FENCE_END.sub("", s)
    s = _LEADING_HTML_WORD.sub("", s)
    s = _DOCTYPE.sub("", s)
    # If a full <body>…</body> pair exists, keep only its inner content (drops
    # the head and anything outside the body).
    m = _BODY.search(s)
    if m:
        s = m.group(1)
    # Drop any <head>…</head> block, then strip ALL residual scaffolding tags —
    # both opening and closing, including a lone <body> with no matching
    # </body> (truncated output).
    s = _HEAD_BLOCK.sub("", s)
    s = _SCAFFOLD_TAGS.sub("", s)
    return s.strip()


# ---------- 3. inline_css ----------

_STYLE_ATTR = re.compile(
    r"""\s+style\s*=\s*(?:"[^"]*"|'[^']*')""", re.IGNORECASE
)
_STYLE_BLOCK = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)


def strip_inline_css(text: str) -> str:
    if not text:
        return text
    s = _STYLE_BLOCK.sub("", text)
    s = _STYLE_ATTR.sub("", s)
    return s


# ---------- 4. html_format ----------

# Opening/closing b|strong|i|em|u tags. The lookahead pins the tag NAME so
# <button>, <br>, <ul>, <img> are never matched.
_FORMAT_TAGS = re.compile(
    r"</?(?:b|strong|i|em|u)(?=[\s/>])[^>]*>", re.IGNORECASE
)


def strip_html_formatting(text: str) -> str:
    if not text:
        return text
    return _FORMAT_TAGS.sub("", text)


# ---------- runner ----------

_FUNCS = {
    "markdown": markdown_to_html,
    "response_start": strip_response_start,
    "inline_css": strip_inline_css,
    "html_format": strip_html_formatting,
}


def apply_operations(value: str, operations: list[str]) -> str:
    """Apply the SELECTED operations to ``value`` in the canonical order."""
    chosen = set(operations)
    out = value
    for op in OPERATIONS:
        if op in chosen:
            out = _FUNCS[op](out)
    return out


def apply_operations_traced(
    value: str, operations: list[str]
) -> tuple[str, list[str]]:
    """Like ``apply_operations`` but also return WHICH operations actually
    changed the value (in canonical order). Lets the run page show, per cell,
    the subset of selected transforms that touched that specific cell."""
    chosen = set(operations)
    out = value
    changed: list[str] = []
    for op in OPERATIONS:
        if op in chosen:
            before = out
            out = _FUNCS[op](out)
            if out != before:
                changed.append(op)
    return out, changed
