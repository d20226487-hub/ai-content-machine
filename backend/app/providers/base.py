from abc import ABC, abstractmethod
from dataclasses import dataclass

# Finish/stop reasons meaning "the model was cut off at the output ceiling",
# across the three response shapes ACM speaks:
#   Gemini (ai_studio, vertex/google)            -> "MAX_TOKENS"
#   OpenAI-compatible (openrouter, github_models)-> "length"
#   Anthropic (vertex/anthropic)                 -> "max_tokens"
# Lives here rather than in a service because db.models needs it too, and a
# service import there would cycle back through app_settings_cache.
TRUNCATION_FINISH_REASONS = frozenset({"max_tokens", "length"})


def is_truncated(finish_reason: str | None) -> bool:
    """True when the provider says the reply hit the output ceiling.

    Case-insensitive: Gemini shouts (``MAX_TOKENS``), the others don't.
    """
    if not finish_reason:
        return False
    return finish_reason.strip().lower() in TRUNCATION_FINISH_REASONS


def gemini_completion_tokens(usage: dict) -> int | None:
    """Billable output tokens from a Gemini ``usageMetadata`` block.

    Gemini reports the answer and the reasoning SEPARATELY —
    ``candidatesTokenCount`` excludes ``thoughtsTokenCount``, and
    ``totalTokenCount`` is the sum of prompt + candidates + thoughts. Google
    bills thinking at the output rate, so charging only for
    ``candidatesTokenCount`` understates the real cost, badly on
    reasoning-heavy calls (measured: 3 answer tokens vs 346 thinking tokens
    on one gemini-2.5-flash request).

    Shared by ai_studio and vertex so the two can't drift — both speak the
    same generateContent response shape.

    Note the contrast with Anthropic, whose ``usage.output_tokens`` already
    includes thinking; that path needs no adjustment.
    """
    answer = _coerce_int(usage.get("candidatesTokenCount"))
    if answer is None:
        # Vertex has historically also spelled it outputTokenCount.
        answer = _coerce_int(usage.get("outputTokenCount"))
    thoughts = _coerce_int(usage.get("thoughtsTokenCount"))
    if answer is None and thoughts is None:
        return None
    known = (answer or 0) + (thoughts or 0)

    # Reconcile against the provider's own total. Verified across
    # gemini-2.5-flash, 3.6-flash, 3.1-flash-lite and 3-flash-preview:
    #   promptTokenCount + candidatesTokenCount + thoughtsTokenCount == totalTokenCount
    # If a future model bills a bucket under a key we don't read (a renamed
    # thinking field, say), total - prompt exceeds what we summed — trust the
    # larger figure so new models can't silently undercount. Never take the
    # smaller: a total that omits a bucket we did read would understate it.
    total = _coerce_int(usage.get("totalTokenCount"))
    prompt = _coerce_int(usage.get("promptTokenCount"))
    if total is not None and prompt is not None:
        return max(known, total - prompt)
    return known


def _coerce_int(v: object) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@dataclass
class GenerationResult:
    text: str
    model: str
    finish_reason: str | None = None
    raw: dict | None = None
    # Populated when the provider returns token usage metadata. Used by the
    # spend-tracking layer (services/usage.py) to compute per-call cost.
    # None means the provider didn't return that count — cost is then
    # best-effort (zero contribution from that bucket).
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Grounding provenance when the call used a retrieval tool (Google Search).
    # Shape: {"queries": [...], "sources": [{"uri","title"}, ...]}. None when the
    # call wasn't grounded or the provider returned no grounding metadata.
    grounding: dict | None = None


@dataclass
class GenerationParams:
    """Common subset; provider implementations may ignore fields they don't support."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    system: str | None = None  # optional system instruction
    # Reasoning-token allowance, for models that bill thinking against the
    # same output budget as the answer (Gemini 2.5, Claude Sonnet 5).
    #   None -> send nothing; use the model's default.
    #   0    -> disable thinking (Gemini: thinkingBudget=0;
    #           Claude: thinking={"type": "disabled"}).
    #   >0   -> Gemini: that many thinking tokens. Claude models that removed
    #           budget_tokens ignore it and keep their default.
    # Left unset by default so a provider whose thinking API we haven't
    # verified (e.g. Gemini 3.x) is never sent a field it might reject.
    thinking_budget: int | None = None
    # Retrieval grounding for this call. None = off. 'google_search' makes the
    # model research the prompt against Google Search and return citations.
    # Only the Vertex Gemini path honors it; other providers ignore it.
    grounding: str | None = None


class ProviderError(RuntimeError):
    """Wraps any provider-side failure (HTTP, auth, quota, malformed response)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        raw: object = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw
        self.headers = headers or {}

    @property
    def retry_after_seconds(self) -> float | None:
        """Parse the Retry-After header (HTTP date or seconds). None if absent/unparseable."""
        v = self.headers.get("retry-after") or self.headers.get("Retry-After")
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            # HTTP-date form is rare for these APIs; ignore for now.
            return None


class BaseProvider(ABC):
    code: str  # 'ai_studio' | 'vertex' | ...

    def __init__(
        self,
        api_key: str,
        *,
        default_model: str | None = None,
        extra_config: dict | None = None,
    ):
        self.api_key = api_key
        self.default_model = default_model
        # Decrypted structured creds for providers that need more than a
        # single API key. ai_studio / openrouter / github_models pass None.
        # Vertex AI reads service_account_json / project_id / location here.
        self.extra_config = extra_config or {}

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        params: GenerationParams | None = None,
    ) -> GenerationResult:
        ...
