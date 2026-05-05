from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorLogListItem(BaseModel):
    id: int
    created_at: datetime
    source: str
    category: str
    user_id: int | None = None
    user_email: str | None = None
    provider: str | None = None
    status_code: int | None = None
    message: str
    resource_type: str | None = None
    resource_id: str | None = None


class ErrorLogDetail(ErrorLogListItem):
    context_json: dict[str, Any]
    stack_trace: str | None = None


class ErrorLogListResponse(BaseModel):
    items: list[ErrorLogListItem]
    total: int
    page: int
    page_size: int


class FrontendErrorReport(BaseModel):
    message: str = Field(..., max_length=4000)
    stack: str | None = Field(None, max_length=20000)
    url: str | None = Field(None, max_length=2000)
    user_agent: str | None = Field(None, max_length=500)
    component: str | None = Field(None, max_length=200)
    extra: dict[str, Any] | None = None


class RetentionResponse(BaseModel):
    days: int
    allowed: list[int]


class RetentionUpdateRequest(BaseModel):
    days: int


class PurgeResponse(BaseModel):
    deleted: int
