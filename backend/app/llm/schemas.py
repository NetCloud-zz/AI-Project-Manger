"""Shared LLM request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class ChatResponse(BaseModel):
    content: str
    model: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    raw: dict | None = None


class StreamDelta(BaseModel):
    """One incremental chunk from a streaming chat completion."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None


class StructuredOutputRequest(BaseModel):
    """Metadata for a structured-output call (used in logs/tests)."""

    schema_name: str = Field(description="Human-readable schema identifier")
