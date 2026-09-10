"""WeCom API response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WeComTokenResponse(BaseModel):
    errcode: int
    errmsg: str
    access_token: str | None = None
    expires_in: int | None = None


class WeComUserInfoResponse(BaseModel):
    errcode: int
    errmsg: str
    UserId: str | None = Field(default=None, alias="UserId")
    OpenId: str | None = Field(default=None, alias="OpenId")
    user_ticket: str | None = None

    model_config = {"populate_by_name": True}

    @property
    def wechat_user_id(self) -> str | None:
        return self.UserId or self.OpenId


class WeComSendMessageResponse(BaseModel):
    errcode: int
    errmsg: str
    invaliduser: str | None = None
