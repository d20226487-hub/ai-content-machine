"""Retry-with-backoff helper for provider calls.

Retries on:
  * 429 (rate-limited) — honors Retry-After header if respect_retry_after=True
  * 5xx (server errors) — exponential backoff with jitter
  * Network errors raised as ProviderError without status_code

Does NOT retry on:
  * 4xx other than 429 (e.g. 400 bad request, 401 unauthorized) — these will
    not improve by waiting, so failing fast surfaces them faster.
"""
from __future__ import annotations

import asyncio
import random

from app.providers.base import BaseProvider, GenerationParams, GenerationResult, ProviderError


def _is_retryable(e: ProviderError) -> bool:
    if e.status_code is None:
        return True  # network-ish error
    if e.status_code == 429:
        return True
    if 500 <= e.status_code < 600:
        return True
    return False


async def call_with_retry(
    provider: BaseProvider,
    *,
    prompt: str,
    model: str | None,
    params: GenerationParams | None,
    retry_max_attempts: int,
    backoff_base_ms: int,
    backoff_jitter_ms: int,
    respect_retry_after: bool,
) -> GenerationResult:
    """Attempt up to (retry_max_attempts + 1) times. Re-raises the final ProviderError."""
    attempt = 0
    last_error: ProviderError | None = None

    while True:
        try:
            return await provider.generate(prompt=prompt, model=model, params=params)
        except ProviderError as e:
            last_error = e
            if not _is_retryable(e) or attempt >= retry_max_attempts:
                raise
            wait = (backoff_base_ms / 1000.0) * (2**attempt)
            wait += random.uniform(0, backoff_jitter_ms / 1000.0)
            if respect_retry_after:
                ra = e.retry_after_seconds
                if ra is not None and ra > wait:
                    wait = ra
            await asyncio.sleep(wait)
            attempt += 1
            # loop and retry
