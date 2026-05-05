from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class TagUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class TagWithStats(BaseModel):
    """A tag plus aggregate usage info for the management page."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prompt_count: int
    last_used: datetime | None  # max(prompts.updated_at) where the prompt has this tag
    created_at: datetime


class TagListResponse(BaseModel):
    items: list[TagWithStats]
    total: int
    page: int
    page_size: int


class TagMergeRequest(BaseModel):
    """Merge the current tag (in URL) into `target_id`. Source is deleted after."""

    target_id: int
