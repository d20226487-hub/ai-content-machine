"""Deterministic cleanup of Google-Docs HTML export.

Google's "export as HTML" produces verbose, chrome-heavy markup: a giant
``<style>`` block, a ``class`` on every element, every text run wrapped in a
``<span>``, and every external link rewritten as a
``https://www.google.com/url?q=<real>&sa=D&...`` redirect. None of that is
useful as publishable post content.

``clean_doc_html`` strips all of it down to a small allow-list of semantic
tags, keeping only ``href`` on links (un-redirected) and ``src``/``alt`` on
images, then collapses the empty wrappers Google leaves behind. It is pure
and deterministic (stdlib ``html.parser`` only — no BeautifulSoup/lxml
dependency) so it is cheap to unit-test against captured export fixtures.

The AI step (services/gdocs_ai) runs *after* this on the cleaned HTML; keeping
cleanup deterministic means the model only deals with meaning (meta
extraction), never with Google's boilerplate.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

# Tags we keep, mapped to the attributes we keep on them. Everything else on
# the tag (class, style, id, dir, role, ...) is dropped.
_KEEP_ATTRS: dict[str, set[str]] = {
    "p": set(),
    "h1": set(), "h2": set(), "h3": set(),
    "h4": set(), "h5": set(), "h6": set(),
    "ul": set(), "ol": set(), "li": set(),
    "blockquote": set(),
    "strong": set(), "em": set(), "b": set(), "i": set(), "u": set(),
    "sub": set(), "sup": set(), "code": set(), "pre": set(),
    "br": set(), "hr": set(),
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "table": set(), "thead": set(), "tbody": set(), "tr": set(),
    "td": set(), "th": set(),
}

# Void (self-closing) elements among the kept tags — no end tag is emitted.
_VOID = {"br", "hr", "img"}

# Tags whose entire subtree (tag + text) is discarded.
_DROP_TREE = {"style", "script", "head", "title", "meta", "link", "noscript"}

# Block tags that, when emptied by cleanup, should be removed rather than
# left as hollow markup.
_EMPTY_STRIPPABLE = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                     "blockquote", "td", "th", "ul", "ol", "span")


def unwrap_google_redirect(url: str) -> str:
    """Turn a ``google.com/url?q=<real>&...`` redirect into ``<real>``.

    Google rewrites every external hyperlink in an exported Doc through this
    redirector. Anything that isn't such a redirect is returned unchanged.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = (parsed.netloc or "").lower()
    if host.endswith("google.com") and parsed.path == "/url":
        q = parse_qs(parsed.query).get("q")
        if q and q[0]:
            return unquote(q[0])
    return url


class _Cleaner(HTMLParser):
    def __init__(self, *, keep_images: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.keep_images = keep_images
        self.out: list[str] = []
        # Stack of (tag, emitted) for every non-void element we entered, so the
        # matching end tag knows whether it should emit a closing tag.
        self._stack: list[tuple[str, bool]] = []
        # Depth counter for a discarded subtree (style/script/head/...).
        self._suppress = 0
        self._suppress_tag: str | None = None

    # -- start tags -------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()

        if self._suppress:
            if tag == self._suppress_tag:
                self._suppress += 1
            return

        if tag in _DROP_TREE:
            if tag in ("meta", "link"):  # void — nothing to suppress
                return
            self._suppress = 1
            self._suppress_tag = tag
            return

        if tag == "img" and not self.keep_images:
            return

        if tag in _KEEP_ATTRS:
            attr_str = self._render_attrs(tag, attrs)
            # An anchor with no usable href is just decoration — unwrap it so
            # its text survives without a dead <a>.
            if tag == "a" and 'href="' not in attr_str:
                self._stack.append((tag, False))
                return
            if tag in _VOID:
                self.out.append(f"<{tag}{attr_str}>")
            else:
                self.out.append(f"<{tag}{attr_str}>")
                self._stack.append((tag, True))
            return

        # Unknown / chrome tag (span, div, body, font, ...): unwrap — keep the
        # children, drop the wrapper.
        if tag not in _VOID:
            self._stack.append((tag, False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # e.g. <br/> or <img .../> written self-closing.
        tag = tag.lower()
        if self._suppress:
            return
        if tag == "img" and not self.keep_images:
            return
        if tag in _KEEP_ATTRS:
            attr_str = self._render_attrs(tag, attrs)
            if tag == "a" and 'href="' not in attr_str:
                return
            self.out.append(f"<{tag}{attr_str}>")

    # -- end tags ---------------------------------------------------------
    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if self._suppress:
            if tag == self._suppress_tag:
                self._suppress -= 1
                if self._suppress == 0:
                    self._suppress_tag = None
            return

        if tag in _VOID:
            return

        # Pop the most recent matching element off our stack so unbalanced
        # markup can't desync us.
        for i in range(len(self._stack) - 1, -1, -1):
            st_tag, emitted = self._stack[i]
            if st_tag == tag:
                if emitted:
                    self.out.append(f"</{tag}>")
                del self._stack[i:]
                return
        # No matching open we tracked — ignore.

    # -- text -------------------------------------------------------------
    def handle_data(self, data: str) -> None:
        if self._suppress:
            return
        if data:
            self.out.append(html.escape(data, quote=False))

    # -- helpers ----------------------------------------------------------
    def _render_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = _KEEP_ATTRS.get(tag, set())
        parts: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed:
                continue
            if value is None:
                continue
            if tag == "a" and name == "href":
                value = unwrap_google_redirect(value)
                # Drop fragment-only hrefs (#cmnt1, #ftnt1, ...): these are
                # Google Docs comment/footnote refs that point nowhere once
                # the content is published, so the anchor unwraps to text.
                if not value.strip() or value.strip().startswith("#"):
                    continue
            if tag == "img" and name == "src":
                value = unwrap_google_redirect(value)
                if not value.strip():
                    continue
            parts.append(f'{name}="{html.escape(value, quote=True)}"')
        return (" " + " ".join(parts)) if parts else ""

    def result(self) -> str:
        return "".join(self.out)


_WS_RUN = re.compile(r"[ \t\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def _strip_empty_blocks(markup: str) -> str:
    """Iteratively remove block tags left empty by cleanup (``<p></p>``,
    ``<p> </p>``, stray unwrapped ``<span></span>`` remnants, ...)."""
    pattern = re.compile(
        r"<(" + "|".join(_EMPTY_STRIPPABLE) + r")(?:\s[^>]*)?>"
        r"(?:\s|&nbsp;| |<br\s*/?>)*"
        r"</\1>",
        re.IGNORECASE,
    )
    prev = None
    cur = markup
    while prev != cur:
        prev = cur
        cur = pattern.sub("", cur)
    return cur


def clean_doc_html(raw_html: str, *, keep_images: bool = True) -> str:
    """Reduce a Google-Docs HTML export to clean, publishable markup.

    Keeps a small allow-list of semantic tags; un-redirects links; keeps (or
    drops, per ``keep_images``) images; strips classes, inline styles, and the
    span/div wrappers; removes the empty blocks left behind. Returns a markup
    string ready to drop into a ``content`` cell.
    """
    if not raw_html or not raw_html.strip():
        return ""
    parser = _Cleaner(keep_images=keep_images)
    parser.feed(raw_html)
    parser.close()
    out = parser.result()

    out = _strip_empty_blocks(out)
    # Normalize whitespace: collapse intra-line runs, drop &nbsp; padding to
    # ordinary spaces, and squeeze excess blank lines.
    out = out.replace(" ", " ").replace("&nbsp;", " ")
    out = _WS_RUN.sub(" ", out)
    out = _BLANK_LINES.sub("\n\n", out)
    return out.strip()


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(markup: str) -> str:
    """Best-effort plain-text rendering of (cleaned) markup.

    Used to give the AI meta-extraction step a compact text view of the top of
    a Doc, and as a fallback when no HTML is needed. Not a full renderer —
    block tags become newlines, the rest is stripped."""
    if not markup:
        return ""
    text = re.sub(r"(?i)<\s*(/p|/h[1-6]|/li|/div|br\s*/?|/tr)\s*>", "\n", markup)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace(" ", " ")
    text = _WS_RUN.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()
