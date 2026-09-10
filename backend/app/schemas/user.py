"""User request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole, UserStatus


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr | None = None
    mobile: str | None = Field(default=None, max_length=32)
    department: str | None = Field(default=None, max_length=128)
    wechat_user_id: str | None = Field(default=None, max_length=128)
    role: UserRole = UserRole.MEMBER


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    mobile: str | None = Field(default=None, max_length=32)
    department: str | None = Field(default=None, max_length=128)
    wechat_user_id: str | None = Field(default=None, max_length=128)
    role: UserRole | None = None
    status: UserStatus | None = None


class UserPasswordReset(BaseModel):
    """Admin-only password reset (does not require the old password)."""

    password: str = Field(min_length=8, max_length=128)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: UserStatus
    oa_admin_id: int | None = None
    created_at: datetime
    updated_at: datetime


class OaSyncResult(BaseModel):
    created: int
    updated: int
    skipped: int
    total_oa: int