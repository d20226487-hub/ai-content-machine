"""CMS client interface.

Phase 1 only implements `test_connection()`. Publishing is added in Phase 2.
Mirrors the providers/ pattern: a fresh client is built per call from a
Domain row, never cached process-wide.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestResult:
    ok: bool
    status_code: int | None
    detail: str
    elapsed_ms: int | None = None


@dataclass
class CacheResult:
    """Outcome of one cache-control request (clear or warm) against a site."""

    ok: bool
    status_code: int | None
    detail: str
    elapsed_ms: int | None = None


@dataclass
class PublishResult:
    ok: bool
    status_code: int | None
    payload_sent: dict[str, Any]
    response_json: dict[str, Any] | None
    cms_post_id: str | None
    cms_post_url: str | None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class CmsError(RuntimeError):
    """Wraps any CMS-side failure (HTTP, auth, malformed response)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw


class CmsClient(ABC):
    """Per-domain client. Construct from a Domain row + decrypted credentials."""

    cms_type: str  # 'wordpress' | 'custom'

    def __init__(self, *, base_url: str, credentials: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials

    @abstractmethod
    async def test_connection(self) -> TestResult: ...

    @abstractmethod
    async def publish_post(
        self,
        *,
        fields: dict[str, Any],
        language: str | None = None,
        profile_name: str | None = None,
    ) -> PublishResult:
        """Publish a single post.

        `fields` is a dict keyed by `publish_config.fields[*].key` (for WP)
        or by `body_template` placeholders (for Custom). The client is
        responsible for shaping these into the CMS-specific payload.
        """
        ...
