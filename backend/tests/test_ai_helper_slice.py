"""AI Helper word-slicing: first N% by words, HTML-block-safe, reconstructable."""
from __future__ import annotations

from app.services.ai_helper_slice import slice_first_words, splice_back, word_count


def test_word_count_ignores_tags():
    assert word_count("<p>one two three</p>") == 3
    assert word_count("one two three") == 3
    assert word_count("") == 0


def test_plaintext_first_10pct():
    text = " ".join(f"w{i}" for i in range(100))  # 100 words
    head, tail = slice_first_words(text, 10)
    assert word_count(head) == 10
    assert head.split() == [f"w{i}" for i in range(10)]
    assert head + tail == text  # exact reconstruction for splice-back


def test_html_cuts_on_block_boundary_not_mid_tag():
    text = "<p>alpha beta gamma</p><p>delta epsilon</p><p>zeta eta theta</p>"
    head, tail = slice_first_words(text, 20)  # 8 words total, target=2 -> first block
    assert head == "<p>alpha beta gamma</p>"
    assert tail == "<p>delta epsilon</p><p>zeta eta theta</p>"
    assert head + tail == text
    # never split a tag
    assert head.count("<p>") == head.count("</p>")


def test_html_accumulates_blocks_until_target():
    text = "<p>a b c</p><p>d e f</p><p>g h i</p>"  # 9 words
    head, tail = slice_first_words(text, 50)  # target=5 -> needs 2 blocks (3+3>=5)
    assert head == "<p>a b c</p><p>d e f</p>"
    assert tail == "<p>g h i</p>"


def test_inline_only_html_sent_whole():
    text = 'Visit <a href="http://x">the site</a> now for more'
    head, tail = slice_first_words(text, 10)
    assert head == text and tail == ""  # no safe block cut -> whole cell


def test_bounds_and_empty():
    assert slice_first_words("a b c", 0) == ("", "a b c")
    assert slice_first_words("a b c", 100) == ("a b c", "")
    assert slice_first_words("", 10) == ("", "")


def test_splice_back_reconstructs_and_replaces():
    text = "<p>intro para</p><p>body one</p><p>body two</p>"
    head, tail = slice_first_words(text, 33)  # 6 words, target=2 -> first block
    assert head == "<p>intro para</p>"
    edited = "<p>EDITED intro</p>"
    assert splice_back(edited, tail) == "<p>EDITED intro</p><p>body one</p><p>body two</p>"
