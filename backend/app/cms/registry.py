"""Build a CmsClient from a Domain row.

Decrypts credentials and dispatches on cms_type. Used by the test endpoint
in Phase 1 and by the publish service in later phases.
"""
from __future__ import annotations

from app.cms.base import CmsClient
from app.cms.custom import CustomCmsClient
from app.cms.wordpress import WordPressClient
from app.core.crypto import decrypt
from app.db.models import Domain


class UnsupportedCms(RuntimeError):
    pass


def get_cms_client(domain: Domain, *, media_cache=None) -> CmsClient:
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
            custom_config=domain.custom_config,
        )

    raise UnsupportedCms(f"cms_type {domain.cms_type!r} is not supported")
