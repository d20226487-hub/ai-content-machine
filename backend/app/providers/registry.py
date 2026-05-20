"""Lookup an enabled provider by code, decrypting its credentials.

Future providers just need to be added to PROVIDERS. Providers that need
structured creds beyond a single API key (e.g. Vertex AI's
service_account_json + project_id + location) read those from
``BaseProvider.extra_config`` — populated here from
``Provider.extra_config_encrypted``.
"""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.db.models import Provider
from app.providers.ai_studio import AIStudioProvider
from app.providers.base import BaseProvider, ProviderError
from app.providers.github_models import GitHubModelsProvider
from app.providers.openrouter import OpenRouterProvider
from app.providers.vertex_ai import VertexAIProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "ai_studio": AIStudioProvider,
    "vertex": VertexAIProvider,
    "openrouter": OpenRouterProvider,
    "github_models": GitHubModelsProvider,
}


class ProviderNotConfigured(ProviderError):
    """Provider exists in the DB but is disabled or has no API key."""


async def get_provider(db: AsyncSession, code: str) -> BaseProvider:
    cls = PROVIDERS.get(code)
    if cls is None:
        raise ProviderError(f"Provider '{code}' is not implemented yet")

    row = (
        await db.execute(select(Provider).where(Provider.code == code))
    ).scalar_one_or_none()
    if row is None:
        raise ProviderError(f"Provider '{code}' is unknown")
    if not row.enabled:
        raise ProviderNotConfigured(f"Provider '{code}' is disabled in Settings")
    # Vertex AI is the one provider where the api_key column can be empty
    # if the admin chose SA-JSON mode instead. Every other provider still
    # requires api_key_encrypted to be set.
    extra_config = _decrypt_extra(row.extra_config_encrypted)
    if not row.api_key_encrypted and not extra_config:
        raise ProviderNotConfigured(
            f"Provider '{code}' has no credentials configured"
        )

    api_key = decrypt(row.api_key_encrypted) if row.api_key_encrypted else ""
    return cls(
        api_key=api_key,
        default_model=row.default_model,
        extra_config=extra_config,
    )


def _decrypt_extra(blob: str | None) -> dict:
    if not blob:
        return {}
    try:
        return json.loads(decrypt(blob))
    except (ValueError, json.JSONDecodeError):
        # Corrupt extra_config shouldn't kill the whole request — surface
        # as "no extra config" and let the per-provider code raise a clear
        # ProviderConfigError when it needs the missing field.
        return {}
