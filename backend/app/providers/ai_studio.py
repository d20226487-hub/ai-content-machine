"""Google AI Studio (generativelanguage.googleapis.com) provider.

Auth: single API key. Endpoint shape:
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}
"""
from typing import Any

import httpx

from app.providers.base import (
    BaseProvider,
    GenerationParams,
    GenerationResult,
    ProviderError,
    gemini_completion_tokens,
)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class AIStudioProvider(BaseProvider):
    code = "ai_studio"

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        params: GenerationParams | None = None,
    ) -> GenerationResult:
        chosen_model = model or self.default_model
        if not chosen_model:
            raise ProviderError("No model specified and no default_model configured")

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }

        gen_config: dict[str, Any] = {}
        if params:
            if params.temperature is not None:
                gen_config["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                gen_config["maxOutputTokens"] = params.max_output_tokens
            if params.top_p is not None:
                gen_config["topP"] = params.top_p
            # On Gemini 2.5, thinking tokens are billed against maxOutputTokens,
            # so leaving thinking dynamic silently eats the answer's allowance.
            # Only emitted when explicitly configured — never guessed — because
            # the thinking knobs differ across Gemini generations.
            if params.thinking_budget is not None:
                gen_config["thinkingConfig"] = {
                    "thinkingBudget": params.thinking_budget
                }
            if params.system:
                body["systemInstruction"] = {"parts": [{"text": params.system}]}
        if gen_config:
            body["generationConfig"] = gen_config

        url = f"{_BASE_URL}/models/{chosen_model}:generateContent"

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(url, params={"key": self.api_key}, json=body)
            except httpx.HTTPError as e:
                raise ProviderError(f"Network error calling AI Studio: {e}") from e

        if resp.status_code >= 400:
            # Don't truncate — the user often needs the full error to fix it.
            raise ProviderError(
                f"AI Studio returned HTTP {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                raw=resp.text,
                headers={k.lower(): v for k, v in resp.headers.items()},
            )

        data = resp.json()
        try:
            candidate = data["candidates"][0]
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"])
            finish = candidate.get("finishReason")
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"Unexpected AI Studio response shape: {e}", raw=data) from e

        usage = data.get("usageMetadata") or {}
        return GenerationResult(
            text=text,
            model=chosen_model,
            finish_reason=finish,
            raw=data,
            prompt_tokens=_safe_int(usage.get("promptTokenCount")),
            # Includes thinking tokens — Gemini reports them separately from
            # candidatesTokenCount but bills them at the output rate.
            completion_tokens=gemini_completion_tokens(usage),
        )


def _safe_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
