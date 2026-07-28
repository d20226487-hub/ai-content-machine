"""AI Helper structured-engine JSON extraction: robust to fences and prose."""
from __future__ import annotations

from app.services.ai_helper_json import extract_json_object


def test_plain_object():
    assert extract_json_object('{"a": "1", "b": "two"}') == {"a": "1", "b": "two"}


def test_json_fence():
    text = '```json\n{"title": "Hi", "desc": "There"}\n```'
    assert extract_json_object(text) == {"title": "Hi", "desc": "There"}


def test_bare_fence():
    text = '```\n{"x": 1}\n```'
    assert extract_json_object(text) == {"x": 1}


def test_prose_around_object():
    text = 'Sure! Here is your JSON:\n{"meta": "value"}\nHope that helps.'
    assert extract_json_object(text) == {"meta": "value"}


def test_braces_inside_string_values():
    # A closing brace inside a string must not end the object early.
    text = '{"code": "func() { return {1}; }", "ok": "yes"}'
    assert extract_json_object(text) == {"code": "func() { return {1}; }", "ok": "yes"}


def test_escaped_quote_inside_string():
    text = r'{"q": "she said \"hi\"", "n": "2"}'
    assert extract_json_object(text) == {"q": 'she said "hi"', "n": "2"}


def test_nested_object():
    text = 'prefix {"outer": {"inner": "v"}, "k": "w"} suffix'
    assert extract_json_object(text) == {"outer": {"inner": "v"}, "k": "w"}


def test_cyrillic_values():
    text = '```json\n{"описание": "Лучшие ставки на спорт"}\n```'
    assert extract_json_object(text) == {"описание": "Лучшие ставки на спорт"}


def test_array_is_rejected():
    assert extract_json_object('["a", "b"]') is None


def test_scalar_is_rejected():
    assert extract_json_object('"just a string"') is None


def test_no_json_returns_none():
    assert extract_json_object("no json here at all") is None
    assert extract_json_object("") is None


def test_takes_first_object_when_multiple():
    text = '{"first": "1"} and then {"second": "2"}'
    assert extract_json_object(text) == {"first": "1"}
