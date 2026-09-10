"""Agent conversation / memory / chat request schemas with OPT-05—09 fields."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.agent_conversation import ConversationStatus, MessageRole, MessageStatus
from app.models.agent_request import AgentRequestStatus

# Align with ~1M-token models (ContextBudget ≈ chars/2). Nginx body limit is 20m.
MAX_AGENT_MESSAGE_CHARS = 2_000_000


def _reject_blank(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be blank")
    return cleaned


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: int | None = None

    @field_validator("title")
    @classmethod
    def _title_strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConversationStatus | None = None
    project_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_nulls(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key in ("title", "status"):
            if key in data and data[key] is None:
                raise ValueError(f"{key} cannot be null")
        return data

    @field_validator("title")
    @classmethod
    def _title_strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_blank(value, field="title")


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    status: ConversationStatus
    project_id: int | None
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_AGENT_MESSAGE_CHARS)
    #: Client-generated id for network retries; same id + same content is idempotent.
    client_request_id: str | None = Field(default=None, min_length=8, max_length=100)

    @field_validator("content")
    @classmethod
    def _content_strip(cls, value: str) -> str:
        return _reject_blank(value, field="content")


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: MessageRole
    content: str
    status: MessageStatus
    tool_calls: list[Any] | None = None
    tool_results: list[Any] | None = None
    cards: list[Any] | None = None
    model: str | None = None
    parent_user_message_id: int | None = None
    regenerated_from_id: int | None = None
    answer_version: int | None = None
    selected_answer_id: int | None = None
    association_status: str = "NORMAL"
    created_at: datetime
    completed_at: datetime | None = None


class SelectAnswerRequest(BaseModel):
    answer_id: int


class SendMessageResponse(BaseModel):
    """Result of posting a user message and getting an assistant reply."""

    conversation: ConversationResponse
    user_message: MessageResponse
    assistant_message: MessageResponse
    tools_used: list[str] = Field(default_factory=list)
    llm_used: bool = False


class AgentChatRequest(BaseModel):
    """Backward-compatible chat endpoint; optionally binds to a conversation."""

    message: str = Field(min_length=1, max_length=MAX_AGENT_MESSAGE_CHARS)
    conversation_id: int | None = None
    client_request_id: str | None = Field(default=None, min_length=8, max_length=100)

    @field_validator("message")
    @classmethod
    def _message_strip(cls, value: str) -> str:
        return _reject_blank(value, field="message")


class AgentChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    llm_used: bool = False
    conversation_id: int | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None


class AgentRequestStatusResponse(BaseModel):
    id: int
    conversation_id: int
    client_request_id: str
    status: AgentRequestStatus
    user_message_id: int | None
    assistant_message_id: int | None
    cancel_requested: bool
    error_code: str | None = None
    assistant_status: MessageStatus | None = None
    assistant_content: str | None = None


class ActiveGenerationResponse(BaseModel):
    """In-flight generation for a conversation (or null fields when idle)."""

    active: bool
    request: AgentRequestStatusResponse | None = None
