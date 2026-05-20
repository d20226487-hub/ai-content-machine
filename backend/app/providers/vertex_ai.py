"""Google Vertex AI provider.

Two auth modes, auto-picked based on which credentials are configured.
The request body shape is identical to AI Studio (Gemini generateContent),
so the only thing that differs across the two modes is the URL + how we
authenticate the request.

  1. Service-account JSON (enterprise) — `extra_config` carries
     ``service_account_json``, ``project_id``, ``location``. We mint a
     short-lived OAuth2 access token via google-auth and POST against the
     regional ``{location}-aiplatform.googleapis.com`` endpoint scoped to
     a project. This is the only path that gets non-Express quota.

  2. Vertex Express (API key) — ``api_key`` is set. We POST against the
     global ``aiplatform.googleapis.com`` endpoint with ``?key=...``. No
     project/location needed. Express quotas are tight (good for trials,
     not production bulk runs).

Errors map to ProviderError with the upstream status code preserved so
the rate-limit retry layer can honor ``Retry-After`` on 429s.

Adapted from drop-sherlock's vertex_ai integration.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.providers.base import (
    BaseProvider,
    GenerationParams,
    GenerationResult,
    ProviderError,
)


# Process-level cache. Keyed by the SA's client_email so swapping the SA
# JSON in Settings (different identity) doesn't keep serving a stale token.
# Token TTL is ~1h; we guard with a 60-second skew.
_VERTEX_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class VertexAIProvider(BaseProvider):
    code = "vertex"

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

        sa_json = (self.extra_config.get("service_account_json") or "").strip()
        api_key = (self.api_key or "").strip()

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
            if params.system:
                body["systemInstruction"] = {"parts": [{"text": params.system}]}
        if gen_config:
            body["generationConfig"] = gen_config

        if sa_json:
            url, headers, params_qs = self._sa_target(sa_json, chosen_model)
        elif api_key:
            url = (
                "https://aiplatform.googleapis.com/v1/"
                f"publishers/google/models/{chosen_model}:generateContent"
            )
            headers = {"Content-Type": "application/json"}
            params_qs = {"key": api_key}
        else:
            raise ProviderError(
                "Vertex AI: neither a service-account JSON nor an API key is "
                "configured. Set one in Settings → Google Vertex AI."
            )

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                resp = await client.post(
                    url, params=params_qs, headers=headers, json=body
                )
            except httpx.HTTPError as e:
                raise ProviderError(f"Network error calling Vertex AI: {e}") from e

        if resp.status_code >= 400:
            raise ProviderError(
                f"Vertex AI returned HTTP {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                raw=resp.text,
                headers={k.lower(): v for k, v in resp.headers.items()},
            )

        data = resp.json()
        try:
            candidate = data["candidates"][0]
            text = "".join(
                part.get("text", "") for part in candidate["content"]["parts"]
            )
            finish = candidate.get("finishReason")
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(
                f"Unexpected Vertex AI response shape: {e}", raw=data
            ) from e

        usage = data.get("usageMetadata") or {}
        return GenerationResult(
            text=text,
            model=chosen_model,
            finish_reason=finish,
            raw=data,
            prompt_tokens=_safe_int(usage.get("promptTokenCount")),
            completion_tokens=_safe_int(
                usage.get("candidatesTokenCount")
                or usage.get("outputTokenCount")
            ),
        )

    def _sa_target(
        self, sa_json: str, model: str
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        project_id = (self.extra_config.get("project_id") or "").strip()
        location = (self.extra_config.get("location") or "").strip()
        if not project_id:
            raise ProviderError(
                "Vertex AI: project_id is required when using service-account JSON. "
                "Set it in Settings → Google Vertex AI."
            )
        if not location:
            raise ProviderError(
                "Vertex AI: location is required when using service-account JSON. "
                "Set it in Settings → Google Vertex AI (e.g. us-central1)."
            )
        token = _mint_vertex_access_token(sa_json)
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/"
            f"publishers/google/models/{model}:generateContent"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return url, headers, {}


def _mint_vertex_access_token(service_account_json: str) -> str:
    """Mint an OAuth2 access token from a service-account JSON, with a
    process-level cache keyed by the SA's client_email.

    Synchronous (google-auth is sync); cheap enough to call from an async
    path without offloading — refresh happens once per ~hour per identity.
    """
    try:
        info = json.loads(service_account_json)
    except json.JSONDecodeError as e:
        raise ProviderError(
            f"Vertex AI: service_account_json is not valid JSON: {e}"
        ) from e
    client_email = info.get("client_email") or ""
    cached = _VERTEX_TOKEN_CACHE.get(client_email)
    now = time.time()
    if cached and cached[1] > now + 60:
        return cached[0]
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise ProviderError(
            "Vertex AI service-account mode requires google-auth — "
            "rebuild the api/worker images so the dependency installs."
        ) from e
    try:
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    except ValueError as e:
        # google-auth raises ValueError for shape issues
        # ("missing fields token_uri", etc.) — surface as a config error so
        # the Settings test panel shows a clear message.
        raise ProviderError(
            f"Vertex AI: service_account_json is invalid: {e}"
        ) from e
    try:
        creds.refresh(Request())
    except Exception as e:  # noqa: BLE001 — surface OAuth2 errors with a readable message
        raise ProviderError(
            f"Vertex AI: failed to mint access token: {e}"
        ) from e
    token = creds.token or ""
    if not token:
        raise ProviderError("Vertex AI: token mint returned an empty token")
    expiry = creds.expiry.timestamp() if creds.expiry else now + 3300
    _VERTEX_TOKEN_CACHE[client_email] = (token, expiry)
    return token


def _safe_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
