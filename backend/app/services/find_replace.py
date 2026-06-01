"""Find / replace matching engine for bulk-table cells.

Matching runs in Python (``re``) rather than Postgres ``~`` on purpose:
users expect real regex (lookahead, backreferences, Python escape rules),
and Postgres only offers POSIX ERE. At current table sizes the cells are
already loaded in one shot elsewhere, so a Python pass is cheap. Revisit
if a table ever crosses ~10k cells.

Semantics:
  * literal mode (``is_regex=False``) — pattern is matched verbatim
    (``re.escape``) and the replacement is inserted literally, so a ``\\1``
    in the replacement is NOT treated as a backreference.
  * regex mode — pattern compiled as-is; replacement honors backreferences.
  * ``whole_cell`` — the pattern must match the ENTIRE cell value
    (``fullmatch``); a replace then swaps the whole value.
  * ``case_sensitive=False`` adds ``re.IGNORECASE``.
"""
from __future__ import annotations

import difflib
import re


class InvalidPattern(ValueError):
    """Raised for an empty pattern, an uncompilable regex, or a pattern that
    matches the empty string (which would make replace behavior surprising)."""


def compile_pattern(
    pattern: str,
    *,
    is_regex: bool,
    case_sensitive: bool,
) -> re.Pattern[str]:
    if not pattern:
        raise InvalidPattern("Pattern is empty.")
    flags = 0 if case_sensitive else re.IGNORECASE
    raw = pattern if is_regex else re.escape(pattern)
    try:
        compiled = re.compile(raw, flags)
    except re.error as e:  # noqa: PERF203
        raise InvalidPattern(f"Invalid regular expression: {e}") from e
    # A pattern that matches the empty string (e.g. ``a*`` or ``.*``) makes
    # occurrence counting and substitution behave in ways that surprise the
    # user (zero-width matches between every character). Reject up front.
    if compiled.search("") is not None:
        raise InvalidPattern("Pattern matches an empty string; refine it.")
    return compiled


def count_matches(
    compiled: re.Pattern[str], value: str, *, whole_cell: bool
) -> int:
    """Occurrences of ``compiled`` in ``value``. whole_cell → 0 or 1."""
    if not value:
        return 0
    if whole_cell:
        return 1 if compiled.fullmatch(value) is not None else 0
    return sum(1 for _ in compiled.finditer(value))


def segment_diff(
    compiled: re.Pattern[str],
    value: str,
    replacement: str,
    *,
    is_regex: bool,
    whole_cell: bool,
) -> tuple[list[dict], list[dict]]:
    """Split ``value`` (old) and its replaced form (new) into highlight
    segments for a diff view.

    Returns ``(old_segments, new_segments)`` where each segment is
    ``{"text": str, "changed": bool}``. In ``old`` the matched spans are
    ``changed=True`` (struck through by the UI); in ``new`` the inserted
    replacement spans are ``changed=True`` (highlighted). Concatenating
    each list reproduces the old / new value exactly — the new side matches
    what ``apply_replace`` wrote.
    """
    old_segs: list[dict] = []
    new_segs: list[dict] = []
    if not value:
        return old_segs, new_segs

    if whole_cell:
        if compiled.fullmatch(value) is None:
            return (
                [{"text": value, "changed": False}],
                [{"text": value, "changed": False}],
            )
        repl_fn = replacement if is_regex else (lambda _m: replacement)
        return (
            [{"text": value, "changed": True}],
            [{"text": compiled.sub(repl_fn, value), "changed": True}],
        )

    pos = 0
    for m in compiled.finditer(value):
        start, end = m.span()
        if start > pos:
            same = value[pos:start]
            old_segs.append({"text": same, "changed": False})
            new_segs.append({"text": same, "changed": False})
        old_segs.append({"text": value[start:end], "changed": True})
        rep = m.expand(replacement) if is_regex else replacement
        new_segs.append({"text": rep, "changed": True})
        pos = end
    if pos < len(value):
        tail = value[pos:]
        old_segs.append({"text": tail, "changed": False})
        new_segs.append({"text": tail, "changed": False})
    return old_segs, new_segs


def drift_segments(new_value: str, current_value: str) -> list[dict]:
    """Segments of ``current_value`` with the parts that differ from
    ``new_value`` marked ``changed=True`` — used to highlight a later manual
    edit on a drifted cell. Char-level diff via difflib; adjacent same-flag
    runs are coalesced so the UI renders tidy spans."""
    sm = difflib.SequenceMatcher(a=new_value or "", b=current_value or "", autojunk=False)
    merged: list[dict] = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if j1 == j2:  # pure deletion — nothing to show on the current side
            continue
        text = current_value[j1:j2]
        changed = tag != "equal"
        if merged and merged[-1]["changed"] == changed:
            merged[-1]["text"] += text
        else:
            merged.append({"text": text, "changed": changed})
    return merged


def diff_segments(old: str, new: str) -> tuple[list[dict], list[dict]]:
    """Two-sided char-level diff of ``old`` vs ``new`` for a side-by-side view.

    Returns ``(old_segments, new_segments)`` where each segment is
    ``{"text": str, "changed": bool}``. In ``old`` the deleted/replaced spans
    are ``changed=True`` (the UI strikes them in red); in ``new`` the
    inserted/replaced spans are ``changed=True`` (highlighted green).
    Concatenating each list reproduces the respective input exactly. Adjacent
    same-flag runs are coalesced for tidy spans.
    """
    sm = difflib.SequenceMatcher(a=old or "", b=new or "", autojunk=False)
    old_segs: list[dict] = []
    new_segs: list[dict] = []

    def push(segs: list[dict], text: str, changed: bool) -> None:
        if not text:
            return
        if segs and segs[-1]["changed"] == changed:
            segs[-1]["text"] += text
        else:
            segs.append({"text": text, "changed": changed})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        same = tag == "equal"
        push(old_segs, (old or "")[i1:i2], not same)
        push(new_segs, (new or "")[j1:j2], not same)
    return old_segs, new_segs


def unified_segments(old: str, new: str) -> list[dict]:
    """Single-pane char-level diff of ``old`` → ``new`` for a "Changes" view.

    Returns a flat list of ``{"text": str, "kind": "equal"|"add"|"del"}``.
    ``add`` spans (insertions/replacements on the new side) render green;
    ``del`` spans (deletions/replacements on the old side) render red and
    struck through; ``equal`` renders plain. A replacement yields a ``del``
    span immediately followed by an ``add`` span. Adjacent same-kind runs are
    coalesced.
    """
    sm = difflib.SequenceMatcher(a=old or "", b=new or "", autojunk=False)
    out: list[dict] = []

    def push(text: str, kind: str) -> None:
        if not text:
            return
        if out and out[-1]["kind"] == kind:
            out[-1]["text"] += text
        else:
            out.append({"text": text, "kind": kind})

    o, n = old or "", new or ""
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push(o[i1:i2], "equal")
        elif tag == "delete":
            push(o[i1:i2], "del")
        elif tag == "insert":
            push(n[j1:j2], "add")
        else:  # replace — show the old span removed, then the new span added
            push(o[i1:i2], "del")
            push(n[j1:j2], "add")
    return out


def apply_replace(
    compiled: re.Pattern[str],
    value: str,
    replacement: str,
    *,
    is_regex: bool,
    whole_cell: bool,
) -> tuple[str, int]:
    """Return ``(new_value, occurrences_replaced)``.

    In literal mode the replacement is inserted verbatim (a ``lambda``
    sidesteps ``re.sub``'s backreference parsing). ``occurrences`` is 0 when
    nothing changed, so callers can skip writing untouched cells.
    """
    if not value:
        return value, 0

    repl = replacement if is_regex else (lambda _m: replacement)

    if whole_cell:
        if compiled.fullmatch(value) is None:
            return value, 0
        new_value = compiled.sub(repl, value)
        return new_value, 1

    new_value, n = compiled.subn(repl, value)
    return new_value, n
