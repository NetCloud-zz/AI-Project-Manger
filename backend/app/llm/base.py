"""LLM provider protocol and shared exceptions."""

from __future__ import annotations

from typing import Protocol

from app.llm.schemas import ChatMessage, ChatResponse


class LLMProvider(Protocol):
    """Transport layer for a single LLM backend."""

    async def chat(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.0,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | dict[str, str] | None = None,
    ) -> ChatResponse: ...


class LLMError(Exception):
    """Base class for LLM gateway failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when no real provider credentials are available."""


class LLMTimeoutError(LLMError):
    """Raised when the upstream model does not respond in time."""


class LLMServerError(LLMError):
    """Raised on upstream 5xx responses."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMInvalidOutputError(LLMError):
    """Raised when model output cannot be parsed into the requested schema."""

    def __init__(self, message: str, *, raw_content: str | None = None) -> None:
        super().__init__(message)
        self.raw_content = raw_content
