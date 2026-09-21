"""Build a CmsClient from a Domain row.

Decrypts credentials and dispatches on cms_type. Used by the test endpoint
in Phase 1 and by the publish service in later phases.
"""
from __future__ import annotations

from app.cms.base import CmsClient
from app.cms.custom import CustomCmsClient
from app.cms.films import NEWS as FILMS_NEWS, FilmsClient
from app.cms.wordpress import WordPressClient
from app.core.crypto import decrypt
from app.db.models import Domain


class UnsupportedCms(RuntimeError):
    pass


def get_cms_client(
    domain: Domain,
    *,
    media_cache=None,
    custom_config_override: dict | None = None,
    page_type: str | None = None,
    operation: str = "create",
) -> CmsClient:
    """Build a CmsClient from a Domain row.

    ``custom_config_override`` (Custom CMS only) swaps the domain's own
    ``custom_config`` for a caller-supplied one — used by bulk publish to
    pin a built-in page type's endpoint + body template (see
    app/cms/custom_page_types.py) without mutating the Domain. Ignored for
    WordPress domains.

    ``page_type`` / ``operation`` (Films only) say which import to run — the
    Films API has one endpoint whose record_type + mode come from the run.
    """
    creds = (
        decrypt(domain.credentials_encrypted)
        if domain.credentials_encrypted
        else None
    )

    if domain.cms_type == "wordpress":
        return WordPressClient(
            base_url=domain.base_url,
            credentials=creds,
            publish_config=domain.publish_config,
            multilingual_plugin=domain.multilingual_plugin,
            media_cache=media_cache,
        )

    if domain.cms_type == "custom":
        return CustomCmsClient(
            base_url=domain.base_url,
            credentials=creds,
            auth_type=domain.auth_type,
            custom_config=(
                custom_config_override
                if custom_config_override is not None
                else domain.custom_config
            ),
        )

    if domain.cms_type == "films":
        return FilmsClient(
            base_url=domain.base_url,
            credentials=creds,
            page_type=page_type or FILMS_NEWS,
            operation=operation,
        )

    raise UnsupportedCms(f"cms_type {domain.cms_type!r} is not supported")
