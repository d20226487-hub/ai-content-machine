"""Per-tool AI spend shaping for the table cost panel.

AI mini-tools (translate, link-fix) log spend under their own usage `source`,
outside the table's bulk-generation cost. ``_build_tool_costs`` turns the
per-source aggregate into the panel's tool list. The SQL is exercised against
the running stack; the ordering, decimal/int coercion, and null-safety (older
events recorded no cost) are pinned here without a database.
"""
from __future__ import annotations

from decimal import Decimal

from app.api.library import _build_tool_costs
from app.schemas.bulk import ToolCostRead


def test_orders_most_expensive_first():
    rows = [
        ("brain_translate", Decimal("0.01"), 100, 200, 3, 0),
        ("brain_fix_links", Decimal("0.05"), 500, 900, 2, 0),
    ]
    out = _build_tool_costs(rows)
    assert [t.source for t in out] == ["brain_fix_links", "brain_translate"]


def test_coerces_types_and_returns_the_model():
    (tool,) = _build_tool_costs(
        [("brain_translate", Decimal("0.0123"), 100, 250, 4, 1)]
    )
    assert isinstance(tool, ToolCostRead)
    assert tool.cost_usd == Decimal("0.0123")
    assert (tool.prompt_tokens, tool.completion_tokens) == (100, 250)
    assert (tool.calls, tool.unpriced_calls) == (4, 1)


def test_null_cost_and_tokens_are_safe():
    # Events from before token capture: cost/tokens come back as None.
    (tool,) = _build_tool_costs([("brain_fix_links", None, None, None, 6, 6)])
    assert tool.cost_usd == Decimal("0")
    assert tool.prompt_tokens == 0
    assert tool.completion_tokens == 0
    # All six calls are unpriced — this is what makes the panel show "$0.00" with
    # an explanatory asterisk rather than pretending the tool was free.
    assert tool.calls == 6
    assert tool.unpriced_calls == 6


def test_empty_when_no_tool_ran():
    assert _build_tool_costs([]) == []


def test_tiebreak_by_source_name_when_costs_equal():
    rows = [
        ("brain_translate", Decimal("0.02"), 0, 0, 1, 0),
        ("brain_fix_links", Decimal("0.02"), 0, 0, 1, 0),
    ]
    # Equal cost → alphabetical source; deterministic order for the UI.
    assert [t.source for t in _build_tool_costs(rows)] == [
        "brain_fix_links",
        "brain_translate",
    ]
