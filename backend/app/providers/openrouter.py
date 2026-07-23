"""OpenRouter — OpenAI-compatible router across many model providers.

Auth: API key from https://openrouter.ai/keys, sent as Bearer.
Models look like 'openai/gpt-4o', 'anthropic/claude-sonnet-4-6', 'google/gemini-2.5-pro'.
"""
from app.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    code = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    # OpenRouter uses these for attribution / leaderboards. Optional but recommended.
    extra_headers = {
        "HTTP-Referer": "https://localhost",  # replace with your real URL when deployed
        "X-Title": "Content Beast",
    }
