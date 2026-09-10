"""Stub provider used when LLM credentials are absent."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.base import LLMNotConfiguredError
from app.llm.schemas import ChatMessage, ChatResponse, StreamDelta


class StubProvider:
    """Placeholder provider; always reports that LLM is not configured."""

    async def chat(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.0,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | dict[str, str] | None = None,
    ) -> ChatResponse:
        del messages, model, temperature, response_format, tools, tool_choice
        msg = "LLM gateway is not configured (LLM_BASE_URL / LLM_API_KEY missing)"
        raise LLMNotConfiguredError(msg)

    async def chat_stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.0,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | dict[str, str] | None = None,
    ) -> AsyncIterator[StreamDelta]:
        del messages, model, temperature, tools, tool_choice
        msg = "LLM gateway is not configured (LLM_BASE_URL / LLM_API_KEY missing)"
        raise LLMNotConfiguredError(msg)
        yield StreamDelta()  # pragma: no cover — make this an async generator
