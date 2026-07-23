"""Blocking generation when a column's prompt variables aren't all mapped.

The pure check — which of a prompt's ``{{variables}}`` a column's variable_map
fails to fill — is pinned here without a DB (same style as the other
resolver-helper tests). The endpoint wiring (preview surfaces the list, enqueue
rejects on it) is exercised against the running stack.
"""
from __future__ import annotations

from app.api.library import _missing_mapped_vars


def test_all_variables_mapped_is_not_blocked():
    tpl = "Write about {{topic}} in a {{tone}} tone."
    assert _missing_mapped_vars(tpl, {"topic": 5, "tone": 6}) == []


def test_reports_the_unmapped_variable():
    tpl = "Write about {{topic}} in a {{tone}} tone."
    assert _missing_mapped_vars(tpl, {"topic": 5}) == ["tone"]


def test_empty_or_null_map_reports_every_variable():
    tpl = "{{alpha}} and {{beta}}"
    assert set(_missing_mapped_vars(tpl, {})) == {"alpha", "beta"}
    assert set(_missing_mapped_vars(tpl, None)) == {"alpha", "beta"}


def test_null_or_falsy_mapping_counts_as_unmapped():
    tpl = "{{a}} {{b}} {{c}}"
    # b -> None and c -> 0 aren't real column ids; only a is genuinely set.
    assert set(_missing_mapped_vars(tpl, {"a": 5, "b": None, "c": 0})) == {"b", "c"}


def test_prompt_without_variables_never_blocks():
    assert _missing_mapped_vars("Just static copy, no variables.", {}) == []
