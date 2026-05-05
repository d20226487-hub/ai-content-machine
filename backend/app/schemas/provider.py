from pydantic import BaseModel, ConfigDict, Field


class ProviderRead(BaseModel):
    """What we send to the client. The API key is never returned — only its presence."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    display_name: str
    enabled: bool
    has_api_key: bool

    default_model: str | None = None
    prompt_creation_model: str | None = None
    available_models: list[str] = []

    requests_per_minute: int
    max_concurrency: int
    batch_size: int
    inter_request_delay_ms: int
    retry_max_attempts: int
    backoff_base_ms: int
    backoff_jitter_ms: int
    respect_retry_after: bool


class ProviderUpdate(BaseModel):
    """All fields optional; only sent fields are updated.

    `api_key` semantics:
      - omitted          -> unchanged
      - non-empty string -> set / overwrite
      - empty string ""  -> clear (remove the stored key)
    """

    enabled: bool | None = None
    api_key: str | None = None  # see docstring

    default_model: str | None = None
    prompt_creation_model: str | None = None
    available_models: list[str] | None = None

    requests_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    max_concurrency: int | None = Field(default=None, ge=1, le=1000)
    batch_size: int | None = Field(default=None, ge=1, le=10_000)
    inter_request_delay_ms: int | None = Field(default=None, ge=0, le=600_000)
    retry_max_attempts: int | None = Field(default=None, ge=0, le=20)
    backoff_base_ms: int | None = Field(default=None, ge=0, le=600_000)
    backoff_jitter_ms: int | None = Field(default=None, ge=0, le=600_000)
    respect_retry_after: bool | None = None


class ConnectionTestRequest(BaseModel):
    """If `api_key` is provided, test that key (handy before saving).
    If omitted, decrypt and test the currently stored key.
    `model` is optional; defaults to the provider's default_model.
    """

    api_key: str | None = None
    model: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    provider_code: str
    model_used: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    sample_output: str | None = None  # short snippet of what came back, if successful
