"""GitHub Models — OpenAI-compatible inference endpoint.

Auth: a GitHub Personal Access Token (fine-grained, with the `models` permission).
Get one at https://github.com/settings/personal-access-tokens
Model IDs look like 'openai/gpt-4o', 'openai/gpt-4o-mini', 'meta/llama-3.1-405b-instruct',
'mistral-ai/mistral-large', etc. — see https://github.com/marketplace/models for the catalog.
"""
from app.providers.openai_compatible import OpenAICompatibleProvider


class GitHubModelsProvider(OpenAICompatibleProvider):
    code = "github_models"
    base_url = "https://models.github.ai/inference"
