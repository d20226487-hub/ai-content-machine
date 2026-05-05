from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    # Populated when the list endpoint is called with ?with_counts=true; null otherwise.
    prompt_count: int | None = None
    subfolder_count: int | None = None


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: int | None = None  # null = top-level
