"""Helpers for agent request / write-operation idempotency (OPT-03)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agent_request import (
    AgentOperation,
    AgentOperationStatus,
    AgentRequest,
    AgentRequestStatus,
)
from app.services.exceptions import DomainValidationError


class RequestConflictError(DomainValidationError):
    """Same client_request_id with a different payload."""


def content_digest(content: str) -> str:
    normalized = (content or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def args_digest(arguments: dict[str, Any] | None) -> str:
    payload = arguments or {}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def make_operation_id(
    *,
    request_id: int,
    tool_name: str,
    arguments: dict[str, Any] | None,
    tool_call_id: str | None,
    sequence: int,
) -> str:
    """Stable id managed by the app.

    Prefer request + tool + args + tool_call_id so retries of the same call
    reuse the id. Fall back to sequence when the model did not supply a call id.
    """
    digest = args_digest(arguments)
    if tool_call_id:
        base = f"{request_id}|{tool_name}|{digest}|{tool_call_id}"
    else:
        base = f"{request_id}|{tool_name}|{digest}|seq:{sequence}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:40]


def get_request_by_client_id(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    client_request_id: str,
) -> AgentRequest | None:
    return db.scalar(
        select(AgentRequest).where(
            AgentRequest.user_id == user_id,
            AgentRequest.conversation_id == conversation_id,
            AgentRequest.client_request_id == client_request_id,
        )
    )


def begin_request(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    client_request_id: str,
    content: str,
) -> tuple[AgentRequest, bool]:
    """Create or reuse a request. Returns (request, is_new).

    Same key + same content → reuse. Same key + different content → 409 conflict.
    """
    digest = content_digest(content)
    preview = (content or "").strip()[:500]
    existing = get_request_by_client_id(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
    )
    if existing is not None:
        if existing.content_digest != digest:
            raise RequestConflictError("同一请求标识对应了不同的消息内容")
        return existing, False

    row = AgentRequest(
        user_id=user_id,
        conversation_id=conversation_id,
        client_request_id=client_request_id,
        content_digest=digest,
        content_preview=preview,
        status=AgentRequestStatus.ACCEPTED,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        raced = get_request_by_client_id(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
        )
        if raced is None:
            raise
        if raced.content_digest != digest:
            raise RequestConflictError("同一请求标识对应了不同的消息内容") from None
        return raced, False
    return row, True


def mark_request_running(db: Session, request: AgentRequest) -> None:
    request.status = AgentRequestStatus.RUNNING
    db.add(request)


def mark_request_finished(
    db: Session,
    request: AgentRequest,
    *,
    status: AgentRequestStatus,
    user_message_id: int | None = None,
    assistant_message_id: int | None = None,
    error_code: str | None = None,
) -> None:
    request.status = status
    request.completed_at = datetime.now(UTC)
    if user_message_id is not None:
        request.user_message_id = user_message_id
    if assistant_message_id is not None:
        request.assistant_message_id = assistant_message_id
    request.error_code = error_code
    db.add(request)


def get_operation(db: Session, operation_id: str) -> AgentOperation | None:
    return db.scalar(select(AgentOperation).where(AgentOperation.operation_id == operation_id))


def record_operation(
    db: Session,
    *,
    request_id: int,
    operation_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    status: AgentOperationStatus,
    result: dict[str, Any],
    tool_call_id: str | None = None,
) -> AgentOperation:
    existing = get_operation(db, operation_id)
    if existing is not None:
        return existing
    row = AgentOperation(
        operation_id=operation_id,
        request_id=request_id,
        tool_name=tool_name,
        args_digest=args_digest(arguments),
        status=status,
        result_json=result,
        tool_call_id=tool_call_id,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        found = get_operation(db, operation_id)
        if found is None:
            raise
        return found
    return row
