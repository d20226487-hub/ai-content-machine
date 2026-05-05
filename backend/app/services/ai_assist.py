"""AI-assisted prompt creation."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Provider
from app.providers.base import GenerationParams, ProviderError
from app.providers.registry import ProviderNotConfigured, get_provider

DRAFT_SYSTEM_PROMPT = (
    "You are an expert prompt engineer. The user describes what they want a "
    "reusable prompt template to do. Write a clear, well-structured prompt "
    "template they can save and reuse. Use {{variable_name}} placeholders for "
    "anything that should be filled in at runtime — for example {{topic}}, "
    "{{tone}}, {{audience}}, {{length}}. Pick variable names that are short, "
    "snake_case, and self-explanatory.\n\n"
    "Return ONLY the prompt template itself. No preamble, no explanation, no "
    "quotes around it, no markdown fences."
)


async def first_enabled_provider_code(db: AsyncSession) -> str | None:
    row = (
        await db.execute(
            select(Provider.code)
            .where(Provider.enabled.is_(True), Provider.api_key_encrypted.is_not(None))
            .order_by(Provider.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def draft_prompt(
    db: AsyncSession, *, description: str, provider_code: str | None, model: str | None
) -> tuple[str, str, str]:
    """Returns (draft_content, provider_used_code, model_used)."""
    code = provider_code or await first_enabled_provider_code(db)
    if not code:
        raise ProviderNotConfigured(
            "No AI provider is enabled. Configure one in Settings first."
        )

    provider = await get_provider(db, code)

    # Determine which model to use for prompt creation specifically
    if model is None:
        row = (
            await db.execute(select(Provider).where(Provider.code == code))
        ).scalar_one()
        model = row.prompt_creation_model or row.default_model

    if not model:
        raise ProviderError(f"No model configured for provider '{code}'")

    user_message = f"Create a prompt template for the following request:\n\n{description}"

    result = await provider.generate(
        prompt=user_message,
        model=model,
        params=GenerationParams(
            temperature=0.7,
            max_output_tokens=1024,
            system=DRAFT_SYSTEM_PROMPT,
        ),
    )

    text = result.text.strip()
    # Strip ```...``` fences just in case the model added them.
    if text.startswith("```") and text.endswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()

    return text, code, result.model
