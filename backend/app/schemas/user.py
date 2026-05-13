from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    role: RoleRead
    created_at: datetime
    # Populated only on rows returned from /users/trash. Null on the
    # normal /users list.
    deleted_at: datetime | None = None


class TrashBulkIds(BaseModel):
    """Body for /users/trash/bulk-restore and /users/trash/bulk."""

    ids: list[int] = Field(default_factory=list, min_length=1, max_length=500)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role_id: int
    is_active: bool = True


class UserUpdate(BaseModel):
    """All fields optional; only sent fields are updated."""

    full_name: str | None = Field(default=None, max_length=120)
    role_id: int | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=200)
