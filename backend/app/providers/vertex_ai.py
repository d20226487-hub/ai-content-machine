"""Google Vertex AI provider.

Vertex serves models from several *publishers* and they do NOT share a
request shape. This provider dispatches on the model id:

  * ``gemini-*`` (and anything else) -> ``publishers/google/...:generateContent``
    with the Gemini body (``contents`` / ``generationConfig``).
  * ``claude-*``                     -> the Anthropic Messages API, via the
    official ``AsyncAnthropicVertex`` client, which targets
    ``publishers/anthropic/...:rawPredict`` under the hood.

Sending a Claude model id down the Gemini path is what produces Vertex's
"model not supported / no access" error even when the project genuinely has
Claude enabled — the model simply does not exist under ``publishers/google``.

Two auth modes, auto-picked based on which credentials are configured:

  1. Service-account JSON (enterprise) — `extra_config` carries
     ``service_account_json``, ``project_id``, ``location``. We mint a
     short-lived OAuth2 access token via google-auth and POST against the
     regional ``{location}-aiplatform.googleapis.com`` endpoint scoped to
     a project. This is the only path that gets non-Express quota, and the
     only one that can reach Claude.

  2. Vertex Express (API key) — ``api_key`` is set. We POST against the
     global ``aiplatform.googleapis.com`` endpoint with ``?key=...``. No
     project/location needed. Express quotas are tight (good for trials,
     not production bulk runs). Gemini only.

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
    gemini_completion_tokens,
)


# Process-level cache. Keyed by the SA's client_email so swapping the SA
# JSON in Settings (different identity) doesn't keep serving a stale token.
# Token TTL is ~1h; we guard with a 60-second skew.
_VERTEX_TOKEN_CACHE: dict[str, tuple[str, float]] = {}

# Same idea for the google-auth credentials object used by the Anthropic
# client. Building one parses the SA's RSA key, so we avoid redoing it per
# call; google-auth refreshes the underlying token internally.
_VERTEX_CREDS_CACHE: dict[str, Any] = {}

# The Anthropic Messages API requires max_tokens. Only used when the caller
# didn't specify one — bulk generation always does.
_ANTHROPIC_DEFAULT_MAX_TOKENS = 8192

# Claude generations that still accept temperature/top_p. Newer models
# (Sonnet 5, Opus 4.7+, Fable 5) reject non-default sampling params with a
# 400, so anything not listed here is called without them.
_SAMPLING_OK_PREFIXES = (
    "claude-sonnet-4",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-haiku-4",
    "claude-3",
)


def _is_anthropic_model(model: str) -> bool:
    """Vertex serves Claude under publishers/anthropic with a different API."""
    return model.strip().lower().startswith("claude")


def _accepts_sampling_params(model: str) -> bool:
    m = model.strip().lower()
    return any(m.startswith(p) for p in _SAMPLING_OK_PREFIXES)


def _anthropic_error(e: Exception, model: str) -> ProviderError:
    """Normalise anthropic SDK exceptions into ProviderError, preserving the
    status code and headers so call_with_retry can honor Retry-After on 429s.
    """
    if isinstance(e, ProviderError):
        return e
    status = getattr(e, "status_code", None)
    headers: dict[str, str] = {}
    resp = getattr(e, "response", None)
    if resp is not None and getattr(resp, "headers", None):
        headers = {k.lower(): v for k, v in resp.headers.items()}
    body = getattr(e, "message", None) or str(e)
    if status is not None:
        return ProviderError(
            f"Vertex AI (Claude) returned HTTP {status} for '{model}': {body}",
            status_code=status,
            raw=body,
            headers=headers,
        )
    # No status -> connection/timeout class. Left without a status_code so the
    # retry layer treats it as a retryable network error.
    return ProviderError(f"Error calling Vertex AI (Claude) '{model}': {body}")


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

        if _is_anthropic_model(chosen_model):
            return await self._generate_anthropic(prompt, chosen_model, params)
        return await self._generate_gemini(prompt, chosen_model, params)

    # ------------------------------------------------------------------
    # Gemini (publishers/google, :generateContent)
    # ------------------------------------------------------------------

    async def _generate_gemini(
        self,
        prompt: str,
        chosen_model: str,
        params: GenerationParams | None,
    ) -> GenerationResult:
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
            # Includes thinking tokens — Gemini reports them separately from
            # candidatesTokenCount but bills them at the output rate.
            completion_tokens=gemini_completion_tokens(usage),
        )

    # ------------------------------------------------------------------
    # Claude (publishers/anthropic, Anthropic Messages API)
    # ------------------------------------------------------------------

    async def _generate_anthropic(
        self,
        prompt: str,
        chosen_model: str,
        params: GenerationParams | None,
    ) -> GenerationResult:
        try:
            from anthropic import AsyncAnthropicVertex
        except ImportError as e:
            raise ProviderError(
                "Claude on Vertex requires the anthropic SDK — rebuild the "
                "api/worker images so `anthropic[vertex]` installs."
            ) from e

        sa_json = (self.extra_config.get("service_account_json") or "").strip()
        if not sa_json:
            # Express (API-key) auth is Gemini-only; the Anthropic endpoint
            # authenticates with Google OAuth2, not ?key=.
            raise ProviderError(
                f"Vertex AI: model '{chosen_model}' is an Anthropic (Claude) model, "
                "which requires service-account authentication. Add the "
                "service-account JSON, project_id and location in "
                "Settings → Google Vertex AI, or pick a Gemini model."
            )
        project_id = (self.extra_config.get("project_id") or "").strip()
        location = (self.extra_config.get("location") or "").strip()
        if not project_id or not location:
            raise ProviderError(
                "Vertex AI: project_id and location are required for Claude "
                "models. Set them in Settings → Google Vertex AI."
            )

        credentials = _vertex_credentials(sa_json)

        # max_tokens is REQUIRED by the Anthropic Messages API (unlike Gemini's
        # optional maxOutputTokens), so fall back rather than omit.
        max_tokens = (
            params.max_output_tokens
            if params and params.max_output_tokens is not None
            else _ANTHROPIC_DEFAULT_MAX_TOKENS
        )

        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if params:
            if params.system:
                kwargs["system"] = params.system
            # Newer Claude models (Sonnet 5, Opus 4.7+) reject temperature/top_p
            # with a 400. Only send them to models known to accept them; an
            # unrecognised claude-* id defaults to omitting, since a missing
            # sampling param is a soft behaviour change but sending one to a
            # model that rejects it is a hard failure.
            if _accepts_sampling_params(chosen_model):
                if params.temperature is not None:
                    kwargs["temperature"] = params.temperature
                if params.top_p is not None:
                    kwargs["top_p"] = params.top_p
            # Claude Sonnet 5 runs adaptive thinking when `thinking` is omitted,
            # and thinking tokens count against max_tokens — the same trap as
            # Gemini 2.5. A budget of 0 turns it off; anything else leaves the
            # model default (a fixed budget_tokens is rejected on these models).
            if params.thinking_budget == 0:
                kwargs["thinking"] = {"type": "disabled"}

        client = AsyncAnthropicVertex(
            project_id=project_id,
            region=location,
            credentials=credentials,
            # ACM's own call_with_retry owns backoff; letting the SDK retry too
            # would multiply attempts and hide 429s from the rate-limit layer.
            max_retries=0,
        )
        try:
            # Streamed, not messages.create(): the SDK refuses a non-streaming
            # request whose max_tokens it estimates could outlast the 10-minute
            # HTTP timeout, and article-length ceilings cross that line
            # ("Streaming is required for operations that may take longer than
            # 10 minutes"). Streaming also keeps the connection alive rather
            # than sitting idle while a long generation runs.
            #
            # We don't need the individual deltas — get_final_message()
            # accumulates them into the same Message that create() returns, so
            # everything below is unchanged.
            async with client.messages.stream(**kwargs) as stream:
                msg = await stream.get_final_message()
        except Exception as e:  # noqa: BLE001 — normalised to ProviderError below
            raise _anthropic_error(e, chosen_model) from e
        finally:
            await client.close()

        text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        usage = getattr(msg, "usage", None)
        return GenerationResult(
            text=text,
            model=chosen_model,
            # "max_tokens" here means the reply was cut off — the truncation
            # check in bulk_generation keys off this.
            finish_reason=getattr(msg, "stop_reason", None),
            raw=msg.model_dump() if hasattr(msg, "model_dump") else None,
            prompt_tokens=_safe_int(getattr(usage, "input_tokens", None)),
            completion_tokens=_safe_int(getattr(usage, "output_tokens", None)),
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


def _vertex_credentials(service_account_json: str) -> Any:
    """Build (and cache) a google-auth credentials object from the stored SA
    JSON. Shared by the Gemini path (which mints a bearer token from it) and
    the Anthropic client (which takes the credentials object directly).
    """
    try:
        info = json.loads(service_account_json)
    except json.JSONDecodeError as e:
        raise ProviderError(
            f"Vertex AI: service_account_json is not valid JSON: {e}"
        ) from e
    client_email = info.get("client_email") or ""
    cached = _VERTEX_CREDS_CACHE.get(client_email)
    if cached is not None:
        return cached
    try:
        from google.oauth2 import service_account
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
    _VERTEX_CREDS_CACHE[client_email] = creds
    return creds


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
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise ProviderError(
            "Vertex AI service-account mode requires google-auth — "
            "rebuild the api/worker images so the dependency installs."
        ) from e
    creds = _vertex_credentials(service_account_json)
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
