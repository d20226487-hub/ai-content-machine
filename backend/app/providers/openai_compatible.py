"""Shared base for providers that speak OpenAI's /chat/completions API.

Both OpenRouter and GitHub Models accept the same request/response shape, so
their concrete classes only have to set base_url and (optionally) extra headers.
"""
from typing import Any

import httpx

from app.providers.base import (
    BaseProvider,
    GenerationParams,
    GenerationResult,
    ProviderError,
)


class OpenAICompatibleProvider(BaseProvider):
    """Subclasses must set `base_url` (no trailing slash, no /chat/completions)."""

    base_url: str = ""  # set by subclass

    # Optional, sent on every request. Subclasses may add to this.
    extra_headers: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        h.update(self.extra_headers)
        return h

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

        messages: list[dict[str, str]] = []
        if params and params.system:
            messages.append({"role": "system", "content": params.system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {"model": chosen_model, "messages": messages}
        if params:
            if params.temperature is not None:
                body["temperature"] = params.temperature
            if params.max_output_tokens is not None:
                body["max_tokens"] = params.max_output_tokens
            if params.top_p is not None:
                body["top_p"] = params.top_p

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(url, headers=self._headers(), json=body)
            except httpx.HTTPError as e:
                raise ProviderError(f"Network error calling {self.code}: {e}") from e

        if resp.status_code >= 400:
            raise ProviderError(
                f"{self.code} returned HTTP {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                raw=resp.text,
                headers={k.lower(): v for k, v in resp.headers.items()},
            )

        try:
            data = resp.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            finish = choice.get("finish_reason")
            model_used = data.get("model", chosen_model)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise ProviderError(
                f"Unexpected {self.code} response shape: {e}", raw=resp.text
            ) from e

        return GenerationResult(
            text=text, model=model_used, finish_reason=finish, raw=data
        )
