"""Normalize transforms for bulk-table cells.

Four deterministic, user-selectable transforms run on cell values. They
ALWAYS run in a fixed canonical order (trim -> strip_scheme -> strip_slashes
-> lowercase) regardless of the order they arrive in. The user picks a SUBSET;
whatever is picked runs in this order — later steps assume earlier ones already
ran (e.g. ``strip_slashes`` runs after ``strip_scheme`` so the leading ``//``
is gone before edge slashes are trimmed).

Surgical string ops on purpose (no URL parser): each transform only touches the
exact characters it targets, so the before/after diff stays clean.

  1. trim          — strip leading/trailing whitespace.
  2. strip_scheme  — remove a leading URL scheme (``https://`` …) and any
                     leading ``//`` (so ``https://example.com/`` -> ``example.com/``).
  3. strip_slashes — strip leading/trailing ``/``.
  4. lowercase     — lowercase the whole value.
"""
from __future__ import annotations

import re

# Canonical order. Selection is a subset, always applied in THIS order.
OPERATIONS: tuple[str, ...] = (
    "trim",
    "strip_scheme",
    "strip_slashes",
    "lowercase",
)


# ---------- 1. trim ----------


def trim(value: str) -> str:
    return value.strip()


# ---------- 2. strip_scheme ----------

# A URL scheme: a letter followed by letters/digits/+/-/. then "://".
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)


def strip_scheme(value: str) -> str:
    s = _SCHEME.sub("", value)
    # Protocol-relative URLs (``//example.com``) — or a scheme that left a
    # leading ``//`` — also get the leading double slash removed.
    if s.startswith("//"):
        s = s[2:]
    return s


# ---------- 3. strip_slashes ----------


def strip_slashes(value: str) -> str:
    return value.strip("/")


# ---------- 4. lowercase ----------


def lowercase(value: str) -> str:
    return value.lower()


# ---------- runner ----------

_FUNCS = {
    "trim": trim,
    "strip_scheme": strip_scheme,
    "strip_slashes": strip_slashes,
    "lowercase": lowercase,
}


def apply_operations(value: str, operations: list[str]) -> str:
    """Apply the SELECTED operations to ``value`` in the canonical order.
    Empty/None value is returned unchanged."""
    if not value:
        return value
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
    the subset of selected transforms that touched that specific cell. Empty/None
    value returns unchanged with no ops."""
    if not value:
        return value, []
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
