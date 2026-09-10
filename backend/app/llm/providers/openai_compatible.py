"""OpenAI-compatible chat completions client (httpx, no vendor SDK)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import LLMServerError, LLMTimeoutError
from app.llm.schemas import ChatMessage, ChatResponse, StreamDelta, ToolCall


class OpenAICompatibleProvider:
    """Calls ``/chat/completions`` on an OpenAI-compatible HTTP gateway."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

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
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            stream=False,
        )
        data = await self._post_json(payload)
        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            raw_tool_calls = message.get("tool_calls") or []
        except (KeyError, IndexError, TypeError) as exc:
            msg = "LLM response missing choices[0].message"
            raise LLMServerError(msg) from exc

        if not isinstance(content, str):
            msg = "LLM response content is not a string"
            raise LLMServerError(msg)

        tool_calls = [_parse_tool_call(item) for item in raw_tool_calls]
        return ChatResponse(content=content, model=model, raw=data, tool_calls=tool_calls)

    async def chat_stream(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float = 0.0,
        tools: list[dict[str, object]] | None = None,
        tool_choice: str | dict[str, str] | None = None,
    ) -> AsyncIterator[StreamDelta]:
        """Yield content / assembled tool-call deltas from a streamed completion."""
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            response_format=None,
            tools=tools,
            tool_choice=tool_choice,
            stream=True,
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        url = f"{self._base_url}/chat/completions"
        timeout = httpx.Timeout(self._timeout, connect=min(30.0, float(self._timeout)))
        tool_acc: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                if response.status_code >= 500:
                    body = (await response.aread()).decode("utf-8", errors="replace")[
                        :500
                    ]
                    msg = f"LLM upstream error: HTTP {response.status_code} — {body}"
                    raise LLMServerError(msg, status_code=response.status_code)
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")[
                        :500
                    ]
                    msg = f"LLM client error: HTTP {response.status_code} — {body}"
                    raise LLMServerError(msg, status_code=response.status_code)

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        if data_str == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice0 = choices[0] if isinstance(choices[0], dict) else {}
                    delta = choice0.get("delta") or {}
                    if not isinstance(delta, dict):
                        delta = {}
                    reason = choice0.get("finish_reason")
                    if isinstance(reason, str) and reason:
                        finish_reason = reason

                    content = delta.get("content")
                    content_piece = content if isinstance(content, str) and content else None

                    raw_tools = delta.get("tool_calls")
                    if isinstance(raw_tools, list):
                        _merge_tool_call_deltas(tool_acc, raw_tools)

                    if content_piece:
                        yield StreamDelta(
                            content=content_piece,
                            model=model,
                            finish_reason=None,
                        )
        except httpx.TimeoutException as exc:
            msg = f"LLM request timed out after {self._timeout}s"
            raise LLMTimeoutError(msg) from exc

        finalized = _finalize_tool_acc(tool_acc)
        if finalized or finish_reason:
            yield StreamDelta(
                content=None,
                tool_calls=finalized,
                finish_reason=finish_reason,
                model=model,
            )

    def _build_payload(
        self,
        *,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        response_format: dict[str, str] | None,
        tools: list[dict[str, object]] | None,
        tool_choice: str | dict[str, str] | None,
        stream: bool,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model,
            "messages": [_serialize_message(message) for message in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return payload

    async def _post_json(self, payload: dict[str, object]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            msg = f"LLM request timed out after {self._timeout}s"
            raise LLMTimeoutError(msg) from exc

        if response.status_code >= 500:
            msg = f"LLM upstream error: HTTP {response.status_code}"
            raise LLMServerError(msg, status_code=response.status_code)

        if response.status_code >= 400:
            msg = f"LLM client error: HTTP {response.status_code} — {response.text[:500]}"
            raise LLMServerError(msg, status_code=response.status_code)

        data = response.json()
        if not isinstance(data, dict):
            msg = "LLM response is not a JSON object"
            raise LLMServerError(msg)
        return data


def _serialize_message(message: ChatMessage) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    return payload


def _parse_tool_call(raw: object) -> ToolCall:
    if not isinstance(raw, dict):
        msg = "Invalid tool call payload"
        raise LLMServerError(msg)
    function = raw.get("function")
    if not isinstance(function, dict):
        msg = "Invalid tool call function payload"
        raise LLMServerError(msg)
    name = function.get("name")
    arguments_raw = function.get("arguments", "{}")
    if not isinstance(name, str):
        msg = "Tool call missing function name"
        raise LLMServerError(msg)
    if isinstance(arguments_raw, str):
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
    elif isinstance(arguments_raw, dict):
        arguments = arguments_raw
    else:
        arguments = {}
    call_id = raw.get("id")
    if not isinstance(call_id, str):
        call_id = "tool_call"
    return ToolCall(id=call_id, name=name, arguments=arguments)


def _merge_tool_call_deltas(acc: dict[int, dict[str, Any]], raw_tools: list[object]) -> None:
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        index_raw = item.get("index", 0)
        index = int(index_raw) if isinstance(index_raw, int | float | str) else 0
        slot = acc.setdefault(index, {"id": None, "name": "", "arguments": ""})
        call_id = item.get("id")
        if isinstance(call_id, str) and call_id:
            slot["id"] = call_id
        function = item.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name:
                slot["name"] = name
            arguments = function.get("arguments")
            if isinstance(arguments, str) and arguments:
                slot["arguments"] = str(slot["arguments"]) + arguments


def _finalize_tool_acc(acc: dict[int, dict[str, Any]]) -> list[ToolCall]:
    if not acc:
        return []
    calls: list[ToolCall] = []
    for index in sorted(acc):
        slot = acc[index]
        name = slot.get("name") or ""
        if not isinstance(name, str) or not name:
            continue
        arguments_raw = slot.get("arguments") or "{}"
        if isinstance(arguments_raw, str):
            try:
                arguments = json.loads(arguments_raw) if arguments_raw else {}
            except json.JSONDecodeError:
                arguments = {}
        elif isinstance(arguments_raw, dict):
            arguments = arguments_raw
        else:
            arguments = {}
        call_id = slot.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"tool_call_{index}"
        calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
    return calls
