from pydantic import BaseModel, Field


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


class GenerateSingleResponse(BaseModel):
    text: str
    rendered_prompt: str  # the prompt actually sent to the model (with variables substituted)
    provider_used: str
    model_used: str
    finish_reason: str | None = None
    missing_variables: list[str] = []  # variables that were left unsubstituted (for transparency)


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
