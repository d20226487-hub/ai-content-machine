"""Autotool per-domain, per-page file token encoding.

The external proxy that downloads our CSV only accepts file names made of ASCII
letters and digits. These tests pin that guarantee plus the encode/decode
round-trip (now including the page ``start`` offset and ``limit`` / page size)
and legacy back-compat.
"""
import base64
import re

import pytest

from app.services.autotool_files import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MIN_PAGE_SIZE,
    clamp_page_size,
    decode_file_token,
    encode_file_token,
)

ALNUM = re.compile(r"\A[A-Za-z0-9]+\Z")

TABLE_TOKEN = "e42235af2c6643609313d4c86a8d348a"

DOMAINS = [
    "clubworldcuplivestreamfree.org",
    "mundialaovivo.net",
    "ouregardercoupedumondedesclubs.org",
    "sub.example.co.uk",
    # full URLs / awkward values must also survive the round-trip
    "https://example.com/path?a=1&b=2",
    "xn--80ak6aa92e.com",  # punycode/IDN
    "site_with_underscore.test",
    "https://example.com/~promo",  # a literal ~ in the value must NOT break decode
    "café.example",  # non-ASCII
]


@pytest.mark.parametrize("domain", DOMAINS)
def test_token_is_alphanumeric_only(domain):
    token = encode_file_token(TABLE_TOKEN, 304, domain, 0, 50)
    assert ALNUM.match(token), f"token has non-alphanumeric chars: {token!r}"
    # explicitly: none of the symbols the proxy rejects
    for bad in ("~", "-", "_", "=", "/", "+", ".", ":"):
        assert bad not in token


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("start", [0, 50, 100, 12345])
def test_round_trip(domain, start):
    token = encode_file_token(TABLE_TOKEN, 304, domain, start, 50)
    assert decode_file_token(token) == (TABLE_TOKEN, 304, domain, start, 50)


@pytest.mark.parametrize("limit", [1, 25, 50, 200, 1000])
def test_round_trip_varies_page_size(limit):
    token = encode_file_token(TABLE_TOKEN, 7, "x.com", 0, limit)
    assert ALNUM.match(token)
    assert decode_file_token(token) == (TABLE_TOKEN, 7, "x.com", 0, limit)


def test_table_token_leads_and_structure_is_exact():
    # The proxy reads the table id off the front, so the token MUST start with
    # the raw table token, then 8-hex column id, 8-hex start, 8-hex limit, then
    # hex(domain).
    token = encode_file_token(TABLE_TOKEN, 304, "mundialenvivo.net", 50, 50)
    assert token.startswith(TABLE_TOKEN)
    assert token == (
        TABLE_TOKEN + "00000130" + "00000032" + "00000032"
        + b"mundialenvivo.net".hex()
    )


def test_pages_have_distinct_tokens():
    a = encode_file_token(TABLE_TOKEN, 304, "x.com", 0, 50)
    b = encode_file_token(TABLE_TOKEN, 304, "x.com", 50, 50)
    assert a != b
    assert decode_file_token(a)[3] == 0
    assert decode_file_token(b)[3] == 50


def test_bare_table_token_decodes_to_none():
    # A whole-table link carries just the 32-char hex token; it's too short to
    # be composite, so it must NOT be decoded (the route serves the full table).
    assert decode_file_token(TABLE_TOKEN) is None


def test_garbage_returns_none():
    assert decode_file_token("short") is None  # below min length
    assert decode_file_token("z" * 70) is None  # right length, not hex
    # right length but odd → can't be byte-aligned hex
    assert (
        decode_file_token(
            TABLE_TOKEN + "00000130" + "00000000" + "00000032" + "6d6"
        )
        is None
    )


def test_legacy_tilde_token_still_decodes_with_no_page():
    # Links minted before paging use <table_token>~<col>~<urlsafe_b64(domain)>
    # and addressed a whole (unpaged) domain — decode returns start/limit None.
    domain = "clubworldcuplivestreamfree.org"
    b64 = base64.urlsafe_b64encode(domain.encode()).decode().rstrip("=")
    legacy = f"{TABLE_TOKEN}~304~{b64}"
    assert decode_file_token(legacy) == (TABLE_TOKEN, 304, domain, None, None)


def test_clamp_page_size():
    assert clamp_page_size(None) == DEFAULT_PAGE_SIZE
    assert clamp_page_size(0) == MIN_PAGE_SIZE
    assert clamp_page_size(-5) == MIN_PAGE_SIZE
    assert clamp_page_size(10_000) == MAX_PAGE_SIZE
    assert clamp_page_size(100) == 100
