"""Find / replace matching engine for bulk-table cells.

Matching runs in Python (``re``) rather than Postgres ``~`` on purpose:
users expect real regex (lookahead, backreferences, Python escape rules),
and Postgres only offers POSIX ERE. At current table sizes the cells are
already loaded in one shot elsewhere, so a Python pass is cheap. Revisit
if a table ever crosses ~10k cells.

Multi-value (paired-dictionary) semantics:
  A run carries a LIST of find→replace pairs, one per line in each textarea.
  Line N of Find maps to line N of Replace; an empty Replace box deletes
  every Find term. A single-value run is just a 1-pair list, so legacy runs
  (and the single-value UI path) round-trip unchanged.

Per-pair semantics:
  * literal mode (``is_regex=False``) — the find is matched verbatim
    (``re.escape``) and that pair's replacement is inserted literally, so a
    ``\\1`` in the replacement is NOT treated as a backreference.
  * regex mode — the find is compiled as-is; the replacement honors
    backreferences against THAT pair's own groups (each pair compiles
    separately, so ``\\1`` always means the pair's first group).
  * ``whole_cell`` — a find must match the ENTIRE cell value (``fullmatch``);
    the first pair (in order) that fullmatches swaps the whole value.
  * ``case_sensitive=False`` adds ``re.IGNORECASE``.

Cascade rule: a cell's ORIGINAL value is scanned left-to-right in a single
pass. At each position the pairs are tried IN ORDER and the first that matches
wins; the matched span is consumed and replaced, and scanning resumes AFTER
it. So a pair's inserted text is never re-scanned by a later pair (cat→dog
followed by dog→bird leaves "cat" as "dog", not "bird").
"""
from __future__ import annotations

import difflib
import re
from typing import Iterator, NamedTuple

# A run with thousands of pairs would make the per-cell O(len * pairs) scan
# pathological; cap it well above any realistic glossary/rebrand sweep.
MAX_PAIRS = 1000


class InvalidPattern(ValueError):
    """Raised for an empty find, an uncompilable regex, a find that matches the
    empty string (which would make replace behavior surprising), too many
    pairs, or a find/replace line-count mismatch."""


class Rule(NamedTuple):
    """One compiled find→replace pair."""

    compiled: re.Pattern[str]
    replacement: str


def _split_lines(text: str) -> list[str]:
    """Split a textarea into one value per line. A single trailing newline is
    tolerated (dropped) so a pasted list doesn't gain a spurious blank pair;
    interior blank lines are preserved (they're meaningful for pairing — e.g.
    a blank replacement line deletes its paired find)."""
    lines = text.split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines.pop()
    return lines


def parse_finds(pattern: str) -> list[str]:
    """The find side as a list of non-empty values (one per line). Raises if
    any line is empty or there are too many."""
    finds = _split_lines(pattern)
    if not finds or any(f == "" for f in finds):
        raise InvalidPattern("Each Find line must be non-empty.")
    if len(finds) > MAX_PAIRS:
        raise InvalidPattern(f"Too many find values (max {MAX_PAIRS}).")
    return finds


def parse_pairs(pattern: str, replacement: str) -> tuple[list[str], list[str]]:
    """Split both textareas into paired find/replace lists.

    An empty Replace box maps every Find to ``""`` (delete). Otherwise the two
    sides must have the same number of lines; any other mismatch raises so the
    user fixes it rather than getting a silently truncated run."""
    finds = parse_finds(pattern)
    if replacement == "":
        return finds, [""] * len(finds)
    replaces = _split_lines(replacement)
    if len(replaces) != len(finds):
        raise InvalidPattern(
            f"{len(finds)} Find line(s) but {len(replaces)} Replace line(s) — "
            "counts must match (leave Replace empty to delete every term)."
        )
    return finds, replaces


def compile_rules(
    finds: list[str],
    replaces: list[str],
    *,
    is_regex: bool,
    case_sensitive: bool,
) -> list[Rule]:
    """Compile equal-length find/replace lists into ordered :class:`Rule`s."""
    flags = 0 if case_sensitive else re.IGNORECASE
    rules: list[Rule] = []
    for find, rep in zip(finds, replaces):
        if not find:
            raise InvalidPattern("Each Find line must be non-empty.")
        raw = find if is_regex else re.escape(find)
        try:
            compiled = re.compile(raw, flags)
        except re.error as e:  # noqa: PERF203
            raise InvalidPattern(f"Invalid regular expression “{find}”: {e}") from e
        # A find that matches the empty string (e.g. ``a*`` or ``.*``) makes
        # occurrence counting and substitution behave in ways that surprise the
        # user (zero-width matches between every character). Reject up front.
        if compiled.search("") is not None:
            raise InvalidPattern(f"“{find}” matches an empty string; refine it.")
        rules.append(Rule(compiled, rep))
    return rules


def _scan(
    rules: list[Rule], value: str, *, whole_cell: bool
) -> Iterator[tuple[re.Match[str], int]]:
    """Yield ``(match, rule_index)`` for each replaced span, left-to-right and
    non-overlapping. At each position the rules are tried in order and the
    first match wins; scanning resumes after the matched span so a rule's
    output is never re-scanned. ``rules`` reject empty-string matches, so every
    yielded span is non-empty and the scan always makes progress."""
    if not value:
        return
    if whole_cell:
        for i, r in enumerate(rules):
            m = r.compiled.fullmatch(value)
            if m is not None:
                yield m, i
                return
        return
    pos = 0
    n = len(value)
    while pos < n:
        for i, r in enumerate(rules):
            m = r.compiled.match(value, pos)
            if m is not None:
                yield m, i
                pos = m.end()
                break
        else:
            pos += 1


def count_matches_rules(
    rules: list[Rule], value: str, *, whole_cell: bool
) -> int:
    """Total occurrences any rule replaces in ``value``. whole_cell → 0 or 1."""
    if not value:
        return 0
    return sum(1 for _ in _scan(rules, value, whole_cell=whole_cell))


def apply_rules(
    rules: list[Rule], value: str, *, is_regex: bool, whole_cell: bool
) -> tuple[str, int]:
    """Return ``(new_value, occurrences_replaced)`` after one left-to-right
    pass. In literal mode each pair's replacement is inserted verbatim (no
    backreference parsing). ``occurrences`` is 0 when nothing changed, so
    callers can skip writing untouched cells."""
    if not value:
        return value, 0
    out: list[str] = []
    pos = 0
    count = 0
    for m, i in _scan(rules, value, whole_cell=whole_cell):
        start, end = m.span()
        out.append(value[pos:start])
        rep = rules[i].replacement
        out.append(m.expand(rep) if is_regex else rep)
        pos = end
        count += 1
    out.append(value[pos:])
    return "".join(out), count


def segment_diff_rules(
    rules: list[Rule], value: str, *, is_regex: bool, whole_cell: bool
) -> tuple[list[dict], list[dict]]:
    """Split ``value`` (old) and its replaced form (new) into highlight
    segments for a diff view.

    Returns ``(old_segments, new_segments)`` where each segment is
    ``{"text": str, "changed": bool}``. In ``old`` the matched spans are
    ``changed=True`` (struck through by the UI); in ``new`` the inserted
    replacement spans are ``changed=True`` (highlighted). Concatenating each
    list reproduces the old / new value exactly — the new side matches what
    ``apply_rules`` wrote."""
    old_segs: list[dict] = []
    new_segs: list[dict] = []
    if not value:
        return old_segs, new_segs

    pos = 0
    for m, i in _scan(rules, value, whole_cell=whole_cell):
        start, end = m.span()
        if start > pos:
            same = value[pos:start]
            old_segs.append({"text": same, "changed": False})
            new_segs.append({"text": same, "changed": False})
        old_segs.append({"text": value[start:end], "changed": True})
        rep = rules[i].replacement
        new_segs.append(
            {"text": m.expand(rep) if is_regex else rep, "changed": True}
        )
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


def aligned_diff(old: str, new: str) -> list[dict]:
    """Aligned char-level diff: ONE list of blocks shared by both sides, each
    ``{"before": str, "after": str, "changed": bool}``.

    Unlike :func:`diff_segments` (two independent per-side lists), every block
    occupies the same position on both sides: for an ``equal`` run
    ``before == after``; for a replace/insert/delete run the two differ and
    either may be empty (a pure deletion has ``after == ""``, a pure insertion
    ``before == ""``). Concatenating the ``before`` fields reproduces ``old``
    and the ``after`` fields reproduce ``new``. Adjacent changed runs coalesce.

    A single aligned list is what lets the fix-run page snippet the Before/After
    panes IN STEP — collapsing the same unchanged stretches on both sides so the
    two snippets stay lined up (a pure deletion no longer snippets one pane while
    leaving the other whole)."""
    sm = difflib.SequenceMatcher(a=old or "", b=new or "", autojunk=False)
    blocks: list[dict] = []

    def push(before: str, after: str, changed: bool) -> None:
        if not before and not after:
            return
        if blocks and blocks[-1]["changed"] == changed:
            blocks[-1]["before"] += before
            blocks[-1]["after"] += after
        else:
            blocks.append({"before": before, "after": after, "changed": changed})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        same = tag == "equal"
        push((old or "")[i1:i2], (new or "")[j1:j2], not same)
    return blocks


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


# Tokens for a coarse-grained diff: a whole HTML tag, a run of whitespace, a
# word, or a single punctuation char. Tokenizing first cuts difflib's input
# from ~thousands of chars to ~hundreds of tokens — and SequenceMatcher is
# ~quadratic, so a big cell diffs ~100x faster with the same visible spans
# (tag/word granularity is also more readable). Every char matches exactly one
# alternative, so "".join(tokens) == original.
_DIFF_TOKEN_RE = re.compile(r"<[^>]+>|\s+|\w+|[^\w\s]")


def unified_segments_tokens(old: str, new: str) -> list[dict]:
    """Same ``{text, kind}`` output as ``unified_segments`` but diffs at TOKEN
    granularity (HTML tags / words / whitespace / punctuation) — far faster on
    large cells. Use for big HTML values; the char-level version stays for
    short cells where per-character precision matters."""
    a = _DIFF_TOKEN_RE.findall(old or "")
    b = _DIFF_TOKEN_RE.findall(new or "")
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out: list[dict] = []

    def push(text: str, kind: str) -> None:
        if not text:
            return
        if out and out[-1]["kind"] == kind:
            out[-1]["text"] += text
        else:
            out.append({"text": text, "kind": kind})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("".join(a[i1:i2]), "equal")
        elif tag == "delete":
            push("".join(a[i1:i2]), "del")
        elif tag == "insert":
            push("".join(b[j1:j2]), "add")
        else:  # replace
            push("".join(a[i1:i2]), "del")
            push("".join(b[j1:j2]), "add")
    return out


def condense_unified(
    old: str, new: str, *, context: int = 48, max_keep: int = 120
) -> list[dict]:
    """A condensed single-pane diff for a long value: like
    ``unified_segments_tokens`` but long UNCHANGED runs are elided to
    ``context`` chars of surrounding
    context with an ellipsis, so the changes stay visible instead of scrolling
    off-screen. Changed (add/del) spans are always kept in full.

    Two-level diff for speed: SequenceMatcher first runs over LINES (cheap —
    ~hundreds of elements, not ~thousands of chars), then only the CHANGED
    line-blocks are re-diffed at token granularity for inline precision. On a
    big multi-line HTML cell this is dramatically faster than a flat
    char/token diff, with the same visible spans.
    """
    a_lines = (old or "").splitlines(keepends=True)
    b_lines = (new or "").splitlines(keepends=True)
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)

    raw: list[dict] = []

    def push(text: str, kind: str) -> None:
        if not text:
            return
        if raw and raw[-1]["kind"] == kind:
            raw[-1]["text"] += text
        else:
            raw.append({"text": text, "kind": kind})

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("".join(a_lines[i1:i2]), "equal")
        elif tag == "delete":
            push("".join(a_lines[i1:i2]), "del")
        elif tag == "insert":
            push("".join(b_lines[j1:j2]), "add")
        else:  # replace — token-diff just the changed block (small) for detail
            for s in unified_segments_tokens(
                "".join(a_lines[i1:i2]), "".join(b_lines[j1:j2])
            ):
                push(s["text"], s["kind"])

    n = len(raw)
    out: list[dict] = []
    for i, s in enumerate(raw):
        if s["kind"] != "equal" or len(s["text"]) <= max_keep:
            out.append(s)
            continue
        text = s["text"]
        has_left = i > 0
        has_right = i < n - 1
        if has_left and has_right:
            text = text[:context] + " … " + text[-context:]
        elif has_right:
            text = "… " + text[-context:]
        else:  # leading-only context, or whole-cell unchanged (shouldn't occur)
            text = text[:context] + " …"
        out.append({"text": text, "kind": "equal"})
    return out


