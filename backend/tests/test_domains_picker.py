"""Schema tests for ``DomainPickerItem`` / ``DomainPickerResponse``.

These pin the lite-shape contract — the wire payload the modal combobox
consumes. Stuff that is *deliberately absent* from the lite shape (the
``publish_config`` and ``custom_config`` blobs) is the primary thing we
want to lock in: regressing back to fat picker responses would silently
re-introduce the "thousands of sites → slow modal" problem the picker
endpoint was added to solve.

Endpoint-level filter / sort / pagination behavior is covered by the
existing integration suite (the API tests under ``tests/`` already
exercise FastAPI routing + a real session); this file just guards the
schema bytes.
"""
from __future__ import annotations

import pytest

from app.schemas.domain import DomainPickerItem, DomainPickerResponse


def test_picker_item_has_only_lite_fields():
    """The lite shape MUST NOT carry publish_config or custom_config —
    they're what the picker exists to avoid serializing."""
    item = DomainPickerItem.model_validate(
        {
            "id": 1,
            "name": "Site A",
            "base_url": "https://a.example.com",
            "cms_type": "wordpress",
            "has_credentials": True,
            "languages": ["en", "ru"],
        }
    )
    dumped = item.model_dump()
    assert set(dumped.keys()) == {
        "id",
        "name",
        "base_url",
        "cms_type",
        "has_credentials",
        "languages",
    }
    # Belt: confirm the two heavy keys are not part of the schema.
    assert "publish_config" not in dumped
    assert "custom_config" not in dumped


def test_picker_item_rejects_unknown_cms_type():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DomainPickerItem.model_validate(
            {
                "id": 1,
                "name": "x",
                "base_url": "https://x",
                "cms_type": "drupal",  # not in the CmsType literal
                "has_credentials": True,
                "languages": [],
            }
        )


def test_picker_response_envelope_shape():
    resp = DomainPickerResponse(
        items=[],
        total=0,
        page=1,
        page_size=50,
        has_more=False,
    )
    dumped = resp.model_dump()
    assert set(dumped.keys()) == {"items", "total", "page", "page_size", "has_more"}


def test_picker_response_has_more_signals_next_page():
    """has_more is the only thing the combobox uses to decide whether to
    fetch the next page — verify the literal it controls flows through."""
    resp = DomainPickerResponse(
        items=[
            DomainPickerItem(
                id=i,
                name=f"d{i}",
                base_url=f"https://d{i}",
                cms_type="wordpress",
                has_credentials=True,
                languages=[],
            )
            for i in range(50)
        ],
        total=123,
        page=1,
        page_size=50,
        has_more=True,
    )
    assert resp.has_more is True
    assert len(resp.items) == 50
