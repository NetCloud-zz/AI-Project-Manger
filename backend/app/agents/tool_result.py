"""Unified tool execution envelope for management agent tools (OPT-02)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    REQUIRES_CHANGE_PROPOSAL = "REQUIRES_CHANGE_PROPOSAL"
    WRITE_DISABLED = "WRITE_DISABLED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    PLAN_REQUIRED = "PLAN_REQUIRED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CHANGE_PLAN_STALE = "CHANGE_PLAN_STALE"
    CHANGE_PLAN_EXPIRED = "CHANGE_PLAN_EXPIRED"
    INVALID_STATE = "INVALID_STATE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DESTRUCTIVE_BLOCKED = "DESTRUCTIVE_BLOCKED"


_RETRYABLE = frozenset(
    {
        ToolErrorCode.DEPENDENCY_UNAVAILABLE,
        ToolErrorCode.TIMEOUT,
        ToolErrorCode.RESULT_UNKNOWN,
        ToolErrorCode.INTERNAL_ERROR,
    }
)

# Map legacy lowercase / snake tokens used in older payloads and tests.
_LEGACY_CODE_ALIASES: dict[str, ToolErrorCode] = {
    "invalid_arguments": ToolErrorCode.INVALID_ARGUMENTS,
    "permission_denied": ToolErrorCode.PERMISSION_DENIED,
    "not_found": ToolErrorCode.NOT_FOUND,
    "unknown_tool": ToolErrorCode.UNKNOWN_TOOL,
    "version_conflict": ToolErrorCode.VERSION_CONFLICT,
    "requires_change_proposal": ToolErrorCode.REQUIRES_CHANGE_PROPOSAL,
    "write_disabled": ToolErrorCode.WRITE_DISABLED,
    "dependency_unavailable": ToolErrorCode.DEPENDENCY_UNAVAILABLE,
    "timeout": ToolErrorCode.TIMEOUT,
    "result_unknown": ToolErrorCode.RESULT_UNKNOWN,
    "tool_failed": ToolErrorCode.INTERNAL_ERROR,
    "internal_error": ToolErrorCode.INTERNAL_ERROR,
    "ambiguous_entity": ToolErrorCode.AMBIGUOUS_ENTITY,
    "confirmation_required": ToolErrorCode.CONFIRMATION_REQUIRED,
    "plan_required": ToolErrorCode.PLAN_REQUIRED,
    "idempotency_conflict": ToolErrorCode.IDEMPOTENCY_CONFLICT,
    "change_plan_stale": ToolErrorCode.CHANGE_PLAN_STALE,
    "change_plan_expired": ToolErrorCode.CHANGE_PLAN_EXPIRED,
    "invalid_state": ToolErrorCode.INVALID_STATE,
    "validation_error": ToolErrorCode.VALIDATION_ERROR,
    "destructive_blocked": ToolErrorCode.DESTRUCTIVE_BLOCKED,
}


class ToolError(BaseModel):
    code: ToolErrorCode
    message: str
    retryable: bool = False

    @classmethod
    def of(
        cls,
        code: ToolErrorCode | str,
        message: str,
        *,
        retryable: bool | None = None,
    ) -> ToolError:
        resolved = (
            code
            if isinstance(code, ToolErrorCode)
            else _LEGACY_CODE_ALIASES.get(str(code).lower(), ToolErrorCode.INTERNAL_ERROR)
        )
        return cls(
            code=resolved,
            message=message,
            retryable=_RETRYABLE.__contains__(resolved) if retryable is None else retryable,
        )


class ToolResult(BaseModel):
    tool_call_id: str | None = None
    operation_id: str | None = None
    ok: bool
    error: ToolError | None = None
    data: Any = None
    effects: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def success(
        cls,
        data: Any = None,
        *,
        tool_call_id: str | None = None,
        operation_id: str | None = None,
        effects: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        return cls(
            tool_call_id=tool_call_id,
            operation_id=operation_id,
            ok=True,
            error=None,
            data=data,
            effects=list(effects or []),
            evidence=list(evidence or []),
        )

    @classmethod
    def failure(
        cls,
        code: ToolErrorCode | str,
        message: str,
        *,
        tool_call_id: str | None = None,
        operation_id: str | None = None,
        retryable: bool | None = None,
        data: Any = None,
        effects: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        return cls(
            tool_call_id=tool_call_id,
            operation_id=operation_id,
            ok=False,
            error=ToolError.of(code, message, retryable=retryable),
            data=data,
            effects=list(effects or []),
            evidence=list(evidence or []),
        )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, default=str)

    def sse_payload(self, *, tool: str, label: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": tool,
            "label": label,
            "success": self.ok,
            "tool_call_id": self.tool_call_id,
            "operation_id": self.operation_id,
        }
        if self.error is not None:
            payload["error_code"] = self.error.code.value
            payload["error_message"] = self.error.message
            payload["retryable"] = self.error.retryable
        return payload

    def storage_record(self, *, name: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "name": name,
            "success": self.ok,
            "tool_call_id": self.tool_call_id,
            "operation_id": self.operation_id,
        }
        if self.error is not None:
            record["error_code"] = self.error.code.value
            record["error_message"] = self.error.message
            record["retryable"] = self.error.retryable
        return record


def parse_tool_result_json(raw: str) -> ToolResult:
    """Parse executor JSON; accept both envelopes and legacy `{error: ...}` payloads."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ToolResult.failure(ToolErrorCode.INTERNAL_ERROR, "工具返回无法解析")
    return coerce_tool_result(payload)


def _is_envelope(payload: dict[str, Any]) -> bool:
    """OPT-02 envelopes always serialize ok/error/data/effects/evidence."""
    return all(key in payload for key in ("ok", "error", "data", "effects", "evidence"))


def coerce_tool_result(payload: Any, *, tool_call_id: str | None = None) -> ToolResult:
    if isinstance(payload, ToolResult):
        if tool_call_id and not payload.tool_call_id:
            return payload.model_copy(update={"tool_call_id": tool_call_id})
        return payload
    if not isinstance(payload, dict):
        return ToolResult.success(payload, tool_call_id=tool_call_id)

    if _is_envelope(payload):
        err = payload.get("error")
        if payload.get("ok") is True:
            return ToolResult.success(
                payload.get("data"),
                tool_call_id=payload.get("tool_call_id") or tool_call_id,
                operation_id=payload.get("operation_id"),
                effects=list(payload.get("effects") or []),
                evidence=list(payload.get("evidence") or []),
            )
        if isinstance(err, dict):
            return ToolResult.failure(
                err.get("code") or ToolErrorCode.INTERNAL_ERROR,
                str(err.get("message") or "工具执行失败"),
                tool_call_id=payload.get("tool_call_id") or tool_call_id,
                operation_id=payload.get("operation_id"),
                retryable=err.get("retryable"),
                data=payload.get("data"),
                effects=list(payload.get("effects") or []),
                evidence=list(payload.get("evidence") or []),
            )
        return ToolResult.failure(
            ToolErrorCode.INTERNAL_ERROR,
            str(payload.get("message") or "工具执行失败"),
            tool_call_id=payload.get("tool_call_id") or tool_call_id,
            operation_id=payload.get("operation_id"),
            data=payload.get("data"),
        )

    # Legacy flat error payloads from older tools / tests.
    if "error" in payload and isinstance(payload.get("error"), str):
        return ToolResult.failure(
            payload["error"],
            str(payload.get("message") or payload["error"]),
            tool_call_id=tool_call_id,
            data={k: v for k, v in payload.items() if k not in {"error", "message"}},
        )

    return ToolResult.success(payload, tool_call_id=tool_call_id)


def unwrap_tool_data(payload: Any) -> Any:
    """Return business payload for stub formatters / legacy test helpers."""
    result = coerce_tool_result(payload)
    if result.ok:
        return result.data
    error = result.error
    assert error is not None
    legacy: dict[str, Any] = {
        "error": error.code.value.lower(),
        "message": error.message,
    }
    if isinstance(result.data, dict):
        legacy.update(result.data)
    return legacy


def public_error_message(exc: BaseException, *, fallback: str = "工具执行失败") -> str:
    """User/model-facing message without SQL, secrets, or full stack traces."""
    text = getattr(exc, "message", None) or str(exc) or fallback
    lowered = text.lower()
    if any(
        token in lowered
        for token in ("select ", "insert ", "update ", "delete ", "traceback", "password", "secret")
    ):
        return fallback
    if len(text) > 400:
        return fallback
    return text
