from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.tag import TagRead


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    content: str
    change_note: str | None
    created_by_id: int | None
    created_by_name: str | None = None
    created_by_email: str | None = None
    created_at: datetime


class PromptVersionSummary(BaseModel):
    """Lightweight version row used in lists (no full content)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    change_note: str | None
    created_by_id: int | None
    created_by_name: str | None = None
    created_by_email: str | None = None
    created_at: datetime


class PromptVersionNoteUpdate(BaseModel):
    """Edit just the change_note on an existing version (retroactive)."""

    change_note: str | None = Field(default=None, max_length=500)


class PromptListItem(BaseModel):
    """Row in the prompt list — current content only, no version history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int | None
    current_version: PromptVersionRead | None
    tags: list[TagRead] = []
    created_by_id: int | None = None
    created_by_name: str | None = None
    created_by_email: str | None = None
    created_at: datetime
    updated_at: datetime
    # Populated only on rows returned from /prompts/trash. Null on the
    # normal /prompts list.
    deleted_at: datetime | None = None


class PromptListResponse(BaseModel):
    """Paginated wrapper for the prompt list."""

    items: list[PromptListItem]
    total: int
    page: int
    page_size: int


class TrashBulkIds(BaseModel):
    """Body for /prompts/trash/bulk-restore and /prompts/trash/bulk."""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


class PromptDetail(BaseModel):
    """Full prompt with current content, all version metadata, and tags."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category_id: int | None
    current_version: PromptVersionRead | None
    versions: list[PromptVersionSummary] = []
    tags: list[TagRead] = []
    variables: list[str] = []  # extracted from current_version.content
    created_by_id: int | None
    created_by_name: str | None = None
    created_by_email: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category_id: int | None = None
    content: str = Field(min_length=1)
    change_note: str | None = Field(default=None, max_length=500)
    tag_ids: list[int] = []


class PromptMetaUpdate(BaseModel):
    """Updates name / category / tags. Does NOT create a new version."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = None  # null clears category
    tag_ids: list[int] | None = None  # null leaves unchanged; [] clears all


class PromptVersionCreate(BaseModel):
    """Creates a new version (i.e. an edit to content)."""

    content: str = Field(min_length=1)
    change_note: str | None = Field(default=None, max_length=500)


class PromptRevert(BaseModel):
    target_version_number: int
    change_note: str | None = Field(default=None, max_length=500)


class PromptDraftRequest(BaseModel):
    description: str = Field(min_length=4, max_length=2000)
    provider_code: str | None = None  # defaults to first enabled provider with a key
    model: str | None = None  # defaults to provider.prompt_creation_model


class PromptDraftResponse(BaseModel):
    draft_content: str
    provider_used: str
    model_used: str
