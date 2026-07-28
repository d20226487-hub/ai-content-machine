"""Shared AI Helper output helpers (v1.1 multi-output), used by the service,
the worker, and the cost preview.

An *output* is one column a run writes/edits, stored on the run as
``{"column_id", "mode"("write"|"edit"), "key", "prompt", "name"}``. Legacy v1
runs stored no ``outputs`` list — ``effective_outputs`` synthesizes a one-entry
list from their ``target_column_id`` / ``mode`` so old runs (and their revert
snapshots and detail views) keep working unchanged.
"""
from __future__ import annotations

from typing import Any


def effective_engine(run: Any) -> str:
    """The run's fan-out engine, defaulting legacy runs to per_output."""
    return getattr(run, "engine", None) or "per_output"


def _norm_output(o: dict) -> dict:
    return {
        "column_id": int(o["column_id"]),
        "mode": "edit" if o.get("mode") == "edit" else "write",
        "key": (o.get("key") or "").strip(),
        "prompt": o.get("prompt") or "",
        "name": o.get("name") or "",
    }


def effective_outputs(run: Any) -> list[dict]:
    """Normalized output list for a run.

    v1.1 runs return their stored ``outputs``; legacy v1 runs (empty list)
    synthesize a single ``write``/``edit`` output from the old target column +
    the run prompt, so one code path serves both.
    """
    raw = getattr(run, "outputs", None) or []
    if raw:
        return [_norm_output(o) for o in raw]
    target = getattr(run, "target_column_id", None)
    if target is None:
        return []
    return [
        {
            "column_id": int(target),
            "mode": "edit" if run.mode == "edit" else "write",
            "key": "value",
            "prompt": run.prompt or "",
            "name": "",
        }
    ]


def build_structured_suffix(outputs: list[dict]) -> str:
    """The instruction appended to the structured engine's base prompt telling
    the model exactly which JSON keys to return, described by column name."""
    keys = ", ".join(f'"{o["key"]}"' for o in outputs)
    lines = "\n".join(
        f'- "{o["key"]}": {o.get("name") or o["key"]}' for o in outputs
    )
    return (
        "\n\nReturn ONLY a JSON object — no markdown, no code fence, no "
        f"explanation — with exactly these keys: {keys}.\n"
        "Each key's value is the content for:\n" + lines
    )
