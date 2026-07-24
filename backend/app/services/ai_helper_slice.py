"""Word-based input slicing for the AI Helper tool.

Sending a fixed fraction of a long cell (e.g. the first 10% of a 2000-word
Content cell) cuts input tokens ~proportionally. The cut must never split an
HTML tag, so:

  * plain text  → cut at the word boundary after the target word count;
  * HTML        → cut after the block (``</p>``, ``</h2>``, ``</li>``…) whose
                  cumulative words cross the target — so markup stays valid;
  * HTML w/o any recognizable block boundary → don't slice (send the whole
    cell) rather than risk breaking inline markup.

``slice_first_words`` returns ``(head, tail)`` with ``head + tail == text``
exactly, so Edit mode can splice the AI's edited ``head`` back onto the
untouched ``tail``.
"""
from __future__ import annotations

import re

# Block-level closing tags we may cut AFTER (keeps the markup well-formed).
_BLOCK_CLOSE = re.compile(
    r"(?i)</(?:p|div|section|article|h[1-6]|li|ul|ol|blockquote|table|tr|pre|figure|figcaption)\s*>"
)
_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"\S+")


def word_count(text: str) -> int:
    """Visible-word count — tags stripped so tag tokens don't inflate it."""
    return len(_WORD.findall(_TAG.sub(" ", text or "")))


def _target(total: int, pct: int) -> int:
    """Ceil of pct% of `total` words, at least 1."""
    return max(1, (total * pct + 99) // 100)


def slice_first_words(text: str, pct: int) -> tuple[str, str]:
    """Split ``text`` into (head, tail): head ≈ the first ``pct``% of its words.

    HTML is cut on a block boundary; plain text on a word boundary; HTML with no
    block boundary is left whole (head=text, tail=""). ``head + tail == text``.
    """
    text = text or ""
    if pct <= 0:
        return "", text
    if pct >= 100 or not text:
        return text, ""

    total = word_count(text)
    if total == 0:
        return text, ""
    target = _target(total, pct)

    has_tags = "<" in text and ">" in text
    if has_tags:
        if not _BLOCK_CLOSE.search(text):
            # Inline-only markup, nothing safe to cut on → send the whole cell.
            return text, ""
        seen = 0
        pos = 0
        for m in _BLOCK_CLOSE.finditer(text):
            end = m.end()
            seen += word_count(text[pos:end])
            if seen >= target:
                return text[:end], text[end:]
            pos = end
        return text, ""  # target past the last block → all head

    # Plain text: cut after the target-th word.
    count = 0
    for m in _WORD.finditer(text):
        count += 1
        if count >= target:
            cut = m.end()
            return text[:cut], text[cut:]
    return text, ""


def splice_back(edited_head: str, tail: str) -> str:
    """Reassemble an Edit-mode cell: the AI's edited head + the untouched tail."""
    return (edited_head or "") + (tail or "")
