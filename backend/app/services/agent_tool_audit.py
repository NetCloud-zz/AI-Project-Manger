"""Phase 1 agent audit: tool-call rows for every management tool invocation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import sanitize_for_audit
from app.models.agent_tool_call import AgentToolCall


def _summarize_result(result: dict[str, Any] | None, *, max_chars: int = 2000) -> dict[str, Any]:
    if not result:
        return {}
    encoded = json.dumps(result, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return result
    return {
        "truncated": True,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "ok": result.get("ok"),
        "error": result.get("error"),
        "keys": sorted(result.keys()),
    }


def record_tool_call(
    db: Session,
    *,
    request_id: int | None,
    conversation_id: int | None,
    user_id: int | None,
    tool_name: str,
    risk_level: str,
    tool_call_id: str | None,
    arguments: dict[str, Any] | None,
    result: dict[str, Any] | None,
    success: bool,
    error_code: str | None,
    duration_ms: int | None,
) -> AgentToolCall:
    row = AgentToolCall(
        request_id=request_id,
        conversation_id=conversation_id,
        user_id=user_id,
        tool_name=tool_name,
        risk_level=risk_level,
        tool_call_id=tool_call_id,
        arguments_json=sanitize_for_audit(arguments or {}),
        result_summary=_summarize_result(result),
        success=success,
        error_code=error_code,
        duration_ms=duration_ms,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return row
