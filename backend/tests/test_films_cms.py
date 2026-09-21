"""Films CMS — the film sites' CSV import API (app.cms.films).

One endpoint (POST /import/api.php, basic auth, multipart ``csv_file`` +
``record_type``) serves three record types: films (news), categories and
comments. Bulk publish sends each row as a one-row CSV so per-row status stays
exact (the API only reports aggregate counts).
"""
from __future__ import annotations

import asyncio
import csv
import io
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.api.publish import _build_curl_preview
from app.cms.films import (
    CATEGORY,
    COMMENT,
    NEWS,
    FilmsClient,
    FilmsClientError,
    build_request,
    normalize_film_url,
)
from app.schemas.publish import BulkPublishRequest


def _csv(text: str) -> dict[str, str]:
    reader = csv.reader(io.StringIO(text))
    header, row = next(reader), next(reader)
    return dict(zip(header, row))


# ---- news (films) -----------------------------------------------------------


def test_news_create_maps_to_import_new_with_api_headers():
    form, text, warnings = build_request(
        NEWS, "create",
        {"title": "Крестный отец", "kp_id_movie": "325", "short_story": "Кратко", "descr": ""},
    )
    assert form == {
        "record_type": "news",
        "mode": "import_new",
        "fields[]": ["kp_id_movie", "title", "short_story"],
    }
    # Headers are the API's own column names; the empty cell is left out so
    # it can't blank the field on the site.
    assert _csv(text) == {
        "Kinopoisk ID": "325", "Title": "Крестный отец", "Краткое описание": "Кратко",
    }
    assert warnings == []


@pytest.mark.parametrize("op,mode", [("update", "update_existing"), ("upsert", "import_and_update")])
def test_news_operations_map_to_modes(op, mode):
    form, _, _ = build_request(NEWS, op, {"title": "X"})
    assert form["mode"] == mode


def test_news_requires_title():
    with pytest.raises(FilmsClientError, match="Title is required"):
        build_request(NEWS, "create", {"kp_id_movie": "1", "title": "  "})


def test_csv_quoting_survives_html_commas_quotes_newlines():
    html = '<p>Он сказал: "да", потом\nушёл</p>'
    _, text, _ = build_request(NEWS, "create", {"title": "A, B", "full_story": html})
    assert _csv(text) == {"Title": "A, B", "Полное описание": html}


# ---- categories -------------------------------------------------------------


def test_category_sends_only_writable_fields_and_identifier_column():
    form, text, _ = build_request(
        CATEGORY, "update",
        {"slug": "comedy", "description": "Смешное", "metatitle": "Комедии"},
    )
    # fields[] is always explicit: without it the API writes EVERY column.
    assert form == {"record_type": "category", "fields[]": ["description", "metatitle"]}
    assert "mode" not in form
    assert _csv(text) == {
        "Category Slug": "comedy",
        "Category Description": "Смешное",
        "Category Meta Title": "Комедии",
    }


def test_category_needs_an_identifier():
    with pytest.raises(FilmsClientError, match="ID, slug or name"):
        build_request(CATEGORY, "update", {"description": "x"})


def test_category_needs_something_to_write():
    with pytest.raises(FilmsClientError, match="Nothing to update"):
        build_request(CATEGORY, "update", {"name": "Комедии"})


def test_category_is_update_only():
    with pytest.raises(FilmsClientError, match="supports only: update"):
        build_request(CATEGORY, "create", {"name": "x", "description": "y"})


# ---- comments ---------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("https://site.com/1671-the-godfather-buck.html", "/the-godfather-buck.html"),
    ("/1671-the-godfather-buck.html", "/the-godfather-buck.html"),
    ("/the-godfather-buck.html", "/the-godfather-buck.html"),
    ("the-godfather-buck.html", "/the-godfather-buck.html"),
    ("https://site.com/films/2001-a-space-odyssey.html", "/a-space-odyssey.html"),
    ("", ""),
])
def test_film_url_normalized_to_alt_name(raw, expected):
    assert normalize_film_url(raw) == expected


def test_comment_pairs_renumbered_and_url_normalized():
    form, text, warnings = build_request(
        COMMENT, "create",
        {
            "film_url": "https://site.com/1671-the-godfather-buck.html",
            "author_1": "Иван", "comment_1": "",          # gap: no text
            "author_2": "Анна", "comment_2": "Шедевр",
            "author_3": "", "comment_3": "Классика",
        },
    )
    assert form == {"record_type": "comment"}  # no mode, no fields[]
    assert _csv(text) == {
        "Film URL": "/the-godfather-buck.html",
        "Film Name": "",
        "Author 1": "Анна", "Comment 1": "Шедевр",
        "Author 2": "", "Comment 2": "Классика",
    }
    assert warnings and "normalized" in warnings[0]


def test_comment_needs_a_film_and_a_comment():
    with pytest.raises(FilmsClientError, match="URL or exact name"):
        build_request(COMMENT, "create", {"comment_1": "x"})
    with pytest.raises(FilmsClientError, match="No comment text"):
        build_request(COMMENT, "create", {"film_name": "Крестный отец"})


def test_comment_is_create_only():
    with pytest.raises(FilmsClientError, match="supports only: create"):
        build_request(COMMENT, "update", {"film_name": "x", "comment_1": "y"})


# ---- request validation -------------------------------------------------------


@pytest.mark.parametrize("page_type,op", [
    ("films_category", "create"),
    ("films_category", "upsert"),
    ("films_comment", "update"),
])
def test_run_request_rejects_unsupported_operation(page_type, op):
    with pytest.raises(ValidationError, match="supports only"):
        BulkPublishRequest(
            table_id=1, mode="single", domain_id=1, operation=op, custom_page_type=page_type,
            row_filter="all",
        )


def test_run_request_accepts_news_upsert():
    BulkPublishRequest(
        table_id=1, mode="single", domain_id=1, operation="upsert", custom_page_type="films_news",
        row_filter="all",
    )


# ---- HTTP round-trip ----------------------------------------------------------


def _publish(handler, *, page_type=NEWS, operation="create", fields=None):
    client = FilmsClient(
        base_url="https://films.example", credentials="admin: s3cret",
        page_type=page_type, operation=operation,
    )
    with patch("app.cms.films.validate_public_url"), patch(
        "app.cms.films.SafeAsyncTransport", lambda: httpx.MockTransport(handler)
    ):
        return asyncio.run(client.publish_post(fields=fields or {"title": "Film"}))


def test_publish_posts_multipart_with_basic_auth_and_reports_success():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True, "data": {"total": 1, "created": 1, "skipped": 0}})

    r = _publish(handler, fields={"title": "Film", "metatitle": "Meta"})
    assert r.ok and r.error is None
    assert seen["url"] == "https://films.example/import/api.php"
    # "admin: s3cret" — the stray space after the colon is normalized away.
    import base64
    assert seen["auth"] == "Basic " + base64.b64encode(b"admin:s3cret").decode()
    assert 'name="csv_file"; filename="row.csv"' in seen["body"]
    assert 'name="record_type"' in seen["body"] and "import_new" in seen["body"]
    assert r.payload_sent["csv_file"] == {"Title": "Film", "Meta Title": "Meta"}
    assert r.cms_post_id is None and r.cms_post_url is None


def test_all_skipped_is_a_failure_with_the_reason():
    r = _publish(
        lambda req: httpx.Response(200, json={"ok": True, "data": {"total": 1, "created": 0, "skipped": 1}}),
        page_type=CATEGORY, operation="update",
        fields={"name": "Комедии", "description": "x"},
    )
    assert not r.ok
    assert "category not found" in r.error


def test_news_create_skip_means_already_exists():
    r = _publish(
        lambda req: httpx.Response(200, json={"ok": True, "data": {"total": 1, "created": 0, "skipped": 1}}),
    )
    assert not r.ok and "already exists" in r.error


def test_401_is_reported_as_bad_credentials():
    r = _publish(lambda req: httpx.Response(401, text="Unauthorized"))
    assert not r.ok and r.status_code == 401 and "login/password" in r.error


def test_redirect_is_not_followed():
    # A 301 would turn the POST into a GET and drop the CSV — surface it.
    r = _publish(lambda req: httpx.Response(301, headers={"location": "https://www.films.example/import/api.php"}))
    assert not r.ok and "redirect" in r.error


def test_ok_false_surfaces_the_sites_message():
    r = _publish(lambda req: httpx.Response(200, json={"ok": False, "error": "bad csv"}))
    assert not r.ok and r.error == "bad csv"


def test_invalid_row_never_hits_the_network():
    def handler(request):  # pragma: no cover — must not be called
        raise AssertionError("request sent")

    r = _publish(handler, fields={"kp_id_movie": "1"})
    assert not r.ok and "Title is required" in r.error


# ---- curl preview -------------------------------------------------------------


def test_curl_preview_is_multipart_with_row_csv():
    job = SimpleNamespace(payload_sent={
        "record_type": "news", "mode": "import_new", "fields[]": ["title", "metatitle"],
        "csv_file": {"Title": "Film, 2", "Meta Title": "M"},
    })
    domain = SimpleNamespace(
        base_url="https://films.example/", cms_type="films", auth_type="basic_auth",
        custom_config=None,
    )
    cp = _build_curl_preview(job, domain)
    assert cp.startswith("cat > row.csv <<'CSV'\nTitle,Meta Title\n\"Film, 2\",M\nCSV\n")
    assert "https://films.example/import/api.php" in cp
    assert "-F 'csv_file=@row.csv'" in cp
    assert "-F 'record_type=news'" in cp and "-F 'mode=import_new'" in cp
    assert "-F 'fields[]=title'" in cp and "-F 'fields[]=metatitle'" in cp
    assert "Basic <REDACTED>" in cp and "application/json" not in cp
