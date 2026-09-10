"""Unified LLM gateway — the only entry point for agents and workers."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMInvalidOutputError, LLMProvider
from app.llm.providers.openai_compatible import OpenAICompatibleProvider
from app.llm.providers.stub import StubProvider
from app.llm.schemas import ChatMessage, ChatResponse, StreamDelta, ToolDefinition
from app.prompts import render_prompt

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Total attempts = 1 + STRUCTURED_OUTPUT_MAX_RETRIES
STRUCTURED_OUTPUT_MAX_RETRIES = 2

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def create_llm_gateway(settings: Settings | None = None) -> LLMGateway:
    """Build a gateway wired to the configured provider."""
    settings = settings or get_settings()
    if settings.llm_configured:
        assert settings.LLM_BASE_URL is not None
        assert settings.LLM_API_KEY is not None
        provider: LLMProvider = OpenAICompatibleProvider(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
    else:
        provider = StubProvider()
    return LLMGateway(provider, settings)


class LLMGateway:
    """Facade over LLM providers; business code must use this instead of vendor SDKs."""

    def __init__(self, provider: LLMProvider, settings: Settings | None = None) -> None:
        self._provider = provider
        self._settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self._settings.llm_configured

    async def chat(
        self,
        *,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        resolved_model = model or self._settings.LLM_MODEL_FAST
        return await self._provider.chat(
            messages=messages,
            model=resolved_model,
            temperature=temperature,
        )

    async def chat_with_tools(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        resolved_model = model or self._settings.LLM_MODEL_REASONING
        tool_payload = _tool_payload(tools)
        return await self._provider.chat(
            messages=messages,
            model=resolved_model,
            temperature=temperature,
            tools=tool_payload,
            tool_choice="auto",
        )

    async def chat_with_tools_stream(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> AsyncIterator[StreamDelta]:
        """Stream a tool-capable completion; provider yields content + final tool_calls."""
        resolved_model = model or self._settings.LLM_MODEL_REASONING
        tool_payload = _tool_payload(tools)
        chat_stream = getattr(self._provider, "chat_stream", None)
        if chat_stream is None:
            response = await self._provider.chat(
                messages=messages,
                model=resolved_model,
                temperature=temperature,
                tools=tool_payload,
                tool_choice="auto",
            )
            if response.content:
                yield StreamDelta(content=response.content, model=resolved_model)
            yield StreamDelta(
                tool_calls=list(response.tool_calls),
                finish_reason="tool_calls" if response.tool_calls else "stop",
                model=resolved_model,
            )
            return

        async for delta in chat_stream(
            messages=messages,
            model=resolved_model,
            temperature=temperature,
            tools=tool_payload,
            tool_choice="auto",
        ):
            yield delta

    async def structured_output(
        self,
        *,
        messages: list[ChatMessage],
        schema: type[T],
        model: str | None = None,
        temperature: float = 0.0,
        max_retries: int = STRUCTURED_OUTPUT_MAX_RETRIES,
    ) -> T:
        """Request JSON matching ``schema``; retry a limited number of times on parse errors."""
        resolved_model = model or self._settings.LLM_MODEL_FAST
        json_instruction = render_prompt(
            "structured_output_instruction",
            schema=schema.model_json_schema(),
        )
        augmented_messages = list(messages)
        if augmented_messages and augmented_messages[-1].role == "user":
            last = augmented_messages[-1]
            augmented_messages[-1] = ChatMessage(
                role="user",
                content=f"{last.content}\n\n{json_instruction}",
            )
        else:
            augmented_messages.append(ChatMessage(role="user", content=json_instruction))

        last_raw: str | None = None
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            response = await self._provider.chat(
                messages=augmented_messages,
                model=resolved_model,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            last_raw = response.content
            try:
                parsed = _parse_json_payload(response.content)
                return schema.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                last_error = str(exc)
                logger.warning(
                    "llm.structured_output.invalid",
                    attempt=attempt + 1,
                    max_attempts=max_retries + 1,
                    error=last_error,
                    raw_preview=response.content[:500],
                )
                if attempt < max_retries:
                    augmented_messages = [
                        *augmented_messages,
                        ChatMessage(role="assistant", content=response.content),
                        ChatMessage(
                            role="user",
                            content=render_prompt(
                                "structured_output_retry",
                                error=last_error,
                            ),
                        ),
                    ]

        msg = f"Failed to obtain valid structured output after {max_retries + 1} attempts"
        raise LLMInvalidOutputError(msg, raw_content=last_raw)


def _parse_json_payload(raw: str) -> object:
    text = raw.strip()
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)


def _tool_payload(tools: list[ToolDefinition]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]
