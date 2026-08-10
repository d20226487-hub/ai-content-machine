from typing import Literal

from pydantic import BaseModel, Field


class GenerationDefaults(BaseModel):
    """Global generation limits (Settings → Generation).

    ``max_output_tokens`` is the ceiling every bulk cell inherits unless its
    column overrides it. ``thinking_budget`` is the reasoning allowance for
    models that bill thinking against that same ceiling (Gemini 2.5, Claude
    Sonnet 5): null sends nothing and keeps the model default, 0 turns
    thinking off so the whole budget goes to the answer.
    """

    max_output_tokens: int = Field(ge=1, le=200000)
    thinking_budget: int | None = Field(default=None, ge=0, le=200000)


class GenerateSingleRequest(BaseModel):
    prompt_id: int
    # Optional version_number; defaults to the prompt's current version.
    version_number: int | None = None
    # Maps prompt variable name -> value (string)
    variables: dict[str, str] = Field(default_factory=dict)
    provider_code: str | None = None  # default: first enabled provider
    model: str | None = None  # default: provider.default_model
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32000)
    # Retrieval grounding for this run. None = off; 'google_search' researches
    # the prompt against Google Search and returns citations. Only the Vertex
    # Gemini path supports it — the endpoint rejects other combinations rather
    # than silently returning an ungrounded answer. Carries a flat per-request
    # surcharge (see services/usage.record_grounding_surcharge).
    grounding: Literal["google_search"] | None = None


class GenerateSingleResponse(BaseModel):
    text: str
    rendered_prompt: str  # the prompt actually sent to the model (with variables substituted)
    provider_used: str
    model_used: str
    finish_reason: str | None = None
    missing_variables: list[str] = []  # variables that were left unsubstituted (for transparency)
    # Grounding provenance when the run was grounded: the search queries the
    # model ran and the web sources it cited, shaped
    # {"queries": [...], "sources": [{"uri","title"}, ...]}. None when grounding
    # was off or the provider returned no grounding metadata.
    grounding_sources: dict | None = None


class RenderPromptRequest(BaseModel):
    """Preview only — no AI call. Returns the rendered prompt for given variables."""

    prompt_id: int
    version_number: int | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class RenderPromptResponse(BaseModel):
    rendered_prompt: str
    expected_variables: list[str]
    missing_variables: list[str]


# ----- Saved generations -----

from datetime import datetime  # noqa: E402

from pydantic import ConfigDict  # noqa: E402


class SavedGenerationListItem(BaseModel):
    """Lightweight row used in lists — no full output, just snippet."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prompt_id: int | None
    prompt_version_number: int | None
    prompt_name_snapshot: str
    provider_code: str
    model_used: str
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class SavedGenerationRead(SavedGenerationListItem):
    """Full saved generation including output and rendered prompt."""

    rendered_prompt: str
    output: str
    variables: dict[str, str]
    finish_reason: str | None
    # Memoized translations of `output` keyed by lowercase language tag.
    # Absent when no translation has been requested for this generation.
    translations: dict[str, dict] | None = None


class SaveGenerationRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    prompt_id: int
    prompt_version_number: int | None = None
    rendered_prompt: str
    output: str
    variables: dict[str, str] = Field(default_factory=dict)
    provider_code: str
    model_used: str
    finish_reason: str | None = None


class SavedGenerationRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class SavedGenerationListResponse(BaseModel):
    """Paginated saved-generation list for the dedicated /create/saved page."""

    items: list[SavedGenerationListItem]
    total: int
    page: int
    page_size: int
