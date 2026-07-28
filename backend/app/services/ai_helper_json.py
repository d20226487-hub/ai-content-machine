"""Robust JSON-object extraction for the AI Helper structured engine.

The structured engine asks the model to "return ONLY a JSON object", but models
routinely wrap it in prose or a ```json fence. ``extract_json_object`` recovers
the object anyway:

  * strips a leading/trailing markdown code fence (``` or ```json);
  * scans for the first ``{`` and returns the first *balanced* ``{...}`` span,
    honouring quoted strings and escapes so braces inside string values don't
    throw off the depth count;
  * ``json.loads`` it, returning the ``dict`` (or ``None`` if nothing parses).

Only a top-level object counts (the engine routes ``obj[key]`` per output); a
bare array or scalar returns ``None``.
"""
from __future__ import annotations

import json


def _strip_fence(text: str) -> str:
    """Drop a single surrounding ```/```json code fence if present."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    # Remove the opening fence line (``` or ```json / ```JSON etc.).
    nl = s.find("\n")
    if nl == -1:
        return s
    s = s[nl + 1 :]
    # Remove the trailing closing fence.
    end = s.rfind("```")
    if end != -1:
        s = s[:end]
    return s.strip()


def _first_balanced_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` substring, or None.

    Tracks string context so ``{`` / ``}`` inside quoted values (and escaped
    quotes) don't corrupt the brace depth.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(text: str) -> dict | None:
    """Best-effort parse of a JSON object from a model reply. None on failure."""
    if not text:
        return None
    candidate = _strip_fence(text)

    # Fast path: the whole (de-fenced) reply is the object.
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass

    # Fallback: pull out the first balanced {...} span and parse that.
    span = _first_balanced_object(candidate)
    if span is None:
        return None
    try:
        obj = json.loads(span)
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None
