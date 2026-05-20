from abc import ABC, abstractmethod
from dataclasses import dataclass


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


@dataclass
class GenerationParams:
    """Common subset; provider implementations may ignore fields they don't support."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    top_p: float | None = None
    system: str | None = None  # optional system instruction


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
