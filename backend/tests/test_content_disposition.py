"""Content-Disposition must survive non-ASCII (e.g. Cyrillic) table names.

Starlette encodes header values as latin-1, so a bare ``filename="Отчёт.csv"``
raised UnicodeEncodeError and 500'd the whole CSV download (deploy-only, because
local test tables have ASCII names). ``content_disposition`` emits an ASCII
fallback plus an RFC 5987 ``filename*``, so the value always latin-1-encodes.
"""
from __future__ import annotations

from app.services.bulk_csv import content_disposition


def test_cyrillic_name_is_latin1_safe():
    value = content_disposition("Отчёт по ссылкам.csv")
    value.encode("latin-1")  # the crash was here — must NOT raise
    assert "filename*=UTF-8''" in value
    assert "%D0%9E" in value  # RFC 5987 percent-encoding of 'О'


def test_ascii_name_keeps_a_clean_fallback():
    value = content_disposition("Fifa 2026 - Matches.csv")
    value.encode("latin-1")
    assert 'filename="Fifa_2026_-_Matches.csv"' in value


def test_all_cyrillic_still_yields_a_usable_ascii_fallback():
    value = content_disposition("Отчёт.csv")
    value.encode("latin-1")
    assert 'filename="' in value  # never empty


def test_inline_flag():
    assert content_disposition("t.csv", inline=True).startswith("inline;")
    assert content_disposition("t.csv").startswith("attachment;")
