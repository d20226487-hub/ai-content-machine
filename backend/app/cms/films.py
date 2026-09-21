"""Films CMS client — the film sites' CSV import API.

Every Films site exposes one endpoint, ``POST {base}/import/api.php``, that
takes a CSV upload (multipart ``csv_file``) plus a ``record_type`` saying what
the CSV holds. Basic auth. The contract comes from the site developer's spec:

  * ``news``     — films. Matched by Kinopoisk ID, then by exact Title.
                   ``mode`` picks create/update/both; ``fields[]`` limits
                   which columns get written.
  * ``category`` — update only (never creates). Matched by ID -> slug -> name.
                   ``fields[]`` limits which of the four texts get written.
  * ``comment``  — attaches Author N / Comment N pairs to an existing film,
                   found by its URL (``alt_name``) or exact title. No ``mode``,
                   no ``fields[]``.

Bulk publish is per-row, so each row goes out as a one-row CSV. That keeps the
per-row status, retry and error reporting the rest of the pipeline relies on:
the API answers with aggregate counts only, so a multi-row CSV couldn't say
WHICH row was skipped.

Field keys (what the bulk mapping panel offers) are the API's own
``fields[]`` names where one exists, so the mapped keys double as the
``fields[]`` list. Only non-empty cells are sent — an empty mapped cell means
"leave it alone", same as Custom CMS dropping empty keys, so an Update never
blanks a field just because the table cell was empty.

The API returns no post id / URL, so there's nothing to write back.
"""
from __future__ import annotations

import base64
import csv
import io
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.cms.base import CmsClient, PublishResult, TestResult
from app.core.ssrf import SafeAsyncTransport, UnsafeUrlError, validate_public_url

ENDPOINT_PATH = "/import/api.php"

NEWS = "films_news"
CATEGORY = "films_category"
COMMENT = "films_comment"
PAGE_TYPES: tuple[str, ...] = (NEWS, CATEGORY, COMMENT)

_RECORD_TYPE = {NEWS: "news", CATEGORY: "category", COMMENT: "comment"}

# Operations each page type allows. Category is update-only and comments are
# create-only by the API's design, not ours.
SUPPORTED_OPERATIONS: dict[str, tuple[str, ...]] = {
    NEWS: ("create", "update", "upsert"),
    CATEGORY: ("update",),
    COMMENT: ("create",),
}

# Bulk operation -> the API's `mode` (news only).
_NEWS_MODE = {
    "create": "import_new",
    "update": "update_existing",
    "upsert": "import_and_update",
}

# How many Author/Comment pairs the mapping offers. The API accepts any number;
# this only bounds the mapping list. Mirrored by FILMS_COMMENT_PAIRS in
# frontend/lib/publishBulk.ts.
COMMENT_PAIRS = 5


@dataclass(frozen=True)
class FilmField:
    key: str      # mapping slot key == API fields[] name (when writable)
    header: str   # CSV column header the API reads


NEWS_FIELDS: tuple[FilmField, ...] = (
    FilmField("kp_id_movie", "Kinopoisk ID"),
    FilmField("title", "Title"),
    FilmField("metatitle", "Meta Title"),
    FilmField("descr", "Meta Description"),
    FilmField("short_story", "Краткое описание"),
    FilmField("full_story", "Полное описание"),
    FilmField("h1_title", "H1"),
    FilmField("poster", "Poster URL"),
)

# id / slug / name only IDENTIFY the category; the other four are what an
# update writes (the only values the API accepts in fields[]).
CATEGORY_FIELDS: tuple[FilmField, ...] = (
    FilmField("id", "Category ID"),
    FilmField("slug", "Category Slug"),
    FilmField("name", "Category Name"),
    FilmField("description", "Category Description"),
    FilmField("metatitle", "Category Meta Title"),
    FilmField("metadescription", "Category Meta Description"),
    FilmField("bottom_description", "Category Bottom Description"),
)
_CATEGORY_IDENTIFIERS = ("id", "slug", "name")
_CATEGORY_WRITABLE = ("description", "metatitle", "metadescription", "bottom_description")

COMMENT_FIELDS: tuple[FilmField, ...] = (
    FilmField("film_url", "Film URL"),
    FilmField("film_name", "Film Name"),
    *(
        f
        for n in range(1, COMMENT_PAIRS + 1)
        for f in (FilmField(f"author_{n}", f"Author {n}"), FilmField(f"comment_{n}", f"Comment {n}"))
    ),
)

FIELDS_BY_PAGE_TYPE: dict[str, tuple[FilmField, ...]] = {
    NEWS: NEWS_FIELDS,
    CATEGORY: CATEGORY_FIELDS,
    COMMENT: COMMENT_FIELDS,
}


def is_films_page_type(value: str | None) -> bool:
    return (value or "") in PAGE_TYPES


class FilmsClientError(ValueError):
    """A row can't be sent as-is (missing required field, nothing to write)."""


def build_request(
    page_type: str, operation: str, fields: dict[str, Any]
) -> tuple[dict[str, Any], str, list[str]]:
    """``(form_data, csv_text, warnings)`` for one row. Pure — unit-tested.

    Raises FilmsClientError when the row can't produce a meaningful request.
    """
    if page_type not in PAGE_TYPES:
        raise FilmsClientError(f"Unknown Films page type {page_type!r}.")
    allowed = SUPPORTED_OPERATIONS[page_type]
    if operation not in allowed:
        raise FilmsClientError(
            f"{_RECORD_TYPE[page_type]!r} supports only: {', '.join(allowed)}."
        )

    values = {
        k: str(v).strip() for k, v in fields.items() if v is not None and str(v).strip()
    }
    warnings: list[str] = []
    form: dict[str, Any] = {"record_type": _RECORD_TYPE[page_type]}
    columns: list[tuple[str, str]] = []  # (header, value)

    if page_type == NEWS:
        if not values.get("title"):
            raise FilmsClientError(
                "Title is required for films (the API matches and creates by it)."
            )
        for f in NEWS_FIELDS:
            if f.key in values:
                columns.append((f.header, values[f.key]))
        form["mode"] = _NEWS_MODE[operation]
        form["fields[]"] = [f.key for f in NEWS_FIELDS if f.key in values]

    elif page_type == CATEGORY:
        if not any(values.get(k) for k in _CATEGORY_IDENTIFIERS):
            raise FilmsClientError("A category needs its ID, slug or name to be found.")
        writable = [k for k in _CATEGORY_WRITABLE if k in values]
        if not writable:
            raise FilmsClientError(
                "Nothing to update: map at least one of description, meta title, "
                "meta description, bottom description."
            )
        for f in CATEGORY_FIELDS:
            if f.key in values:
                columns.append((f.header, values[f.key]))
        # Always explicit — without fields[] the API writes EVERY column, which
        # would blank the texts this row didn't map.
        form["fields[]"] = writable

    else:  # COMMENT
        # Sent exactly as written. The API matches the film's alt_name
        # ("/the-godfather-buck.html"); we deliberately don't rewrite links —
        # stripping a "1671-" id prefix can't be told apart from an alt_name
        # that itself starts with digits ("/2001-a-space-odyssey.html").
        film_url = values.get("film_url", "")
        if not film_url and not values.get("film_name"):
            raise FilmsClientError("A comment needs the film's URL or exact name.")
        columns.append(("Film URL", film_url))
        columns.append(("Film Name", values.get("film_name", "")))
        # Pairs are renumbered consecutively: the API reads Author 1, 2, 3...
        # and a gap (empty comment 2, filled comment 3) would lose the rest.
        n = 0
        for i in range(1, COMMENT_PAIRS + 1):
            text = values.get(f"comment_{i}")
            if not text:
                continue
            n += 1
            columns.append((f"Author {n}", values.get(f"author_{i}", "")))
            columns.append((f"Comment {n}", text))
        if n == 0:
            raise FilmsClientError("No comment text to post.")

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([h for h, _ in columns])
    writer.writerow([v for _, v in columns])
    return form, buf.getvalue(), warnings


def _parse_response(
    resp: httpx.Response,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code == 401:
        return False, body, "401 — wrong login/password for this Films site."
    if resp.status_code >= 400 or not isinstance(body, dict):
        snippet = (resp.text or "")[:300]
        return False, body if isinstance(body, dict) else None, (
            f"HTTP {resp.status_code}: {snippet}".strip()
        )
    if not body.get("ok"):
        msg = body.get("error") or body.get("message") or "The site answered ok=false."
        return False, body, str(msg)
    return True, body, None


class FilmsClient(CmsClient):
    cms_type = "films"

    def __init__(
        self,
        *,
        base_url: str,
        credentials: str | None,
        page_type: str = NEWS,
        operation: str = "create",
    ) -> None:
        super().__init__(base_url=base_url, credentials=credentials)
        self.page_type = page_type
        self.operation = operation

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}{ENDPOINT_PATH}"

    def _auth_header(self) -> dict[str, str]:
        if not self.credentials:
            return {}
        login, sep, password = self.credentials.partition(":")
        clean = f"{login.strip()}:{password.strip()}" if sep else self.credentials
        token = base64.b64encode(clean.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    async def test_connection(self) -> TestResult:
        # GET has no side effects; all it can tell us is whether the endpoint
        # exists and accepts the credentials (401 = rejected).
        start = time.perf_counter()
        try:
            validate_public_url(self.endpoint)
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.get(self.endpoint, headers=self._auth_header())
        except UnsafeUrlError as e:
            return TestResult(ok=False, status_code=None, detail=f"URL rejected: {e}")
        except httpx.HTTPError as e:
            return TestResult(ok=False, status_code=None, detail=f"Network error: {e}")
        elapsed = int((time.perf_counter() - start) * 1000)
        code = resp.status_code
        if code == 401:
            return TestResult(False, code, "401 — login/password rejected.", elapsed)
        if code == 404:
            return TestResult(False, code, f"No import API at {self.endpoint} (404).", elapsed)
        if code >= 500:
            return TestResult(False, code, f"HTTP {code} from {self.endpoint}.", elapsed)
        return TestResult(
            True, code, f"Import API reachable, credentials accepted (HTTP {code}).", elapsed
        )

    async def publish_post(
        self,
        *,
        fields: dict[str, Any],
        language: str | None = None,
        profile_name: str | None = None,
    ) -> PublishResult:
        try:
            form, csv_text, warnings = build_request(self.page_type, self.operation, fields)
        except FilmsClientError as e:
            return PublishResult(
                ok=False, status_code=None, payload_sent={}, response_json=None,
                cms_post_id=None, cms_post_url=None, error=str(e),
            )

        # What the run-detail page shows as "sent": the form fields plus the
        # CSV rendered as a header -> value map (readable, unlike raw CSV).
        reader = csv.reader(io.StringIO(csv_text))
        header, row = next(reader), next(reader)
        payload_sent: dict[str, Any] = {**form, "csv_file": dict(zip(header, row))}

        def fail(msg: str, code: int | None = None, body: Any = None) -> PublishResult:
            return PublishResult(
                ok=False, status_code=code, payload_sent=payload_sent,
                response_json=body, cms_post_id=None, cms_post_url=None,
                error=msg, warnings=warnings,
            )

        try:
            validate_public_url(self.endpoint)
            # No redirect following: a 301/302 turns the POST into a GET and
            # silently drops the upload. Report it instead.
            async with httpx.AsyncClient(
                timeout=60.0, follow_redirects=False, transport=SafeAsyncTransport()
            ) as client:
                resp = await client.post(
                    self.endpoint,
                    headers=self._auth_header(),
                    data=form,
                    files={"csv_file": ("row.csv", csv_text.encode("utf-8"), "text/csv")},
                )
        except UnsafeUrlError as e:
            return fail(f"URL rejected: {e}")
        except httpx.HTTPError as e:
            return fail(f"Network error: {e}")

        if 300 <= resp.status_code < 400:
            loc = resp.headers.get("location", "")
            return fail(
                f"HTTP {resp.status_code} redirect to {loc} — fix the domain's base URL "
                "(following a redirect would drop the uploaded CSV).",
                resp.status_code,
            )

        ok, body, error = _parse_response(resp)
        if ok:
            data = (body or {}).get("data") or {}
            done = sum(int(data.get(k) or 0) for k in ("created", "updated"))
            skipped = int(data.get("skipped") or 0)
            if skipped and not done:
                reason = {
                    NEWS: (
                        "Skipped: the film already exists (Create only adds new ones)."
                        if self.operation == "create"
                        else "Skipped: film not found by Kinopoisk ID or exact title."
                    ),
                    CATEGORY: "Skipped: category not found by ID, slug or name.",
                    COMMENT: "Skipped: film not found by URL or exact title.",
                }[self.page_type]
                return fail(
                    f"{reason} Details: import/logs/import.log on the site.",
                    resp.status_code, body,
                )
            return PublishResult(
                ok=True, status_code=resp.status_code, payload_sent=payload_sent,
                response_json=body, cms_post_id=None, cms_post_url=None,
                warnings=warnings,
            )
        return fail(error or "Publish failed.", resp.status_code, body)
