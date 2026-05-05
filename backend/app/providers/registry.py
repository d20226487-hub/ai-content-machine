"""Lookup an enabled provider by code, decrypting its API key.

Future providers (vertex, github_models, openrouter) just need to be added to PROVIDERS.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt
from app.db.models import Provider
from app.providers.ai_studio import AIStudioProvider
from app.providers.base import BaseProvider, ProviderError
from app.providers.github_models import GitHubModelsProvider
from app.providers.openrouter import OpenRouterProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "ai_studio": AIStudioProvider,
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
    if not row.api_key_encrypted:
        raise ProviderNotConfigured(f"Provider '{code}' has no API key configured")

    api_key = decrypt(row.api_key_encrypted)
    return cls(api_key=api_key, default_model=row.default_model)
