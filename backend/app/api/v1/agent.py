"""Project Assistant — chat and conversation APIs."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.stream_events import encode_sse
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.agent_conversation import ConversationStatus
from app.models.user import User
from app.schemas.agent import (
    ActiveGenerationResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentRequestStatusResponse,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    SelectAnswerRequest,
    SendMessageResponse,
)
from app.schemas.agent_command import CommandRetryInput
from app.schemas.agent_memory import MemoryCreate, MemoryResponse, MemoryUpdate
from app.services.agent_idempotency import RequestConflictError
from app.services.conversation import ConversationService
from app.services.exceptions import (
    AgentMessageNotFoundError,
    ConversationNotFoundError,
    DomainValidationError,
    MemoryNotFoundError,
)
from app.services.memory import MemoryService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/requests/{request_id}/plan")
def get_command_plan(
    request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    from app.services.agent_commands import CommandService

    service = CommandService(db)
    try:
        return service.snapshot(service.owned(request_id, current_user))
    except DomainValidationError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.post("/requests/{request_id}/plan/retry")
async def retry_command_plan(
    request_id: int,
    body: CommandRetryInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.agent_conversation import AgentConversation
    from app.models.agent_request import AgentRequest
    from app.services.agent_commands import CommandService

    service = CommandService(db)
    try:
        plan = service.owned(request_id, current_user)
        request = db.get(AgentRequest, request_id)
        conversation = db.get(AgentConversation, request.conversation_id)
        if conversation is None or conversation.status == ConversationStatus.ARCHIVED:
            raise DomainValidationError("归档对话不可恢复写入")
        service.retry(plan, body)
        return await service.run(plan, current_user)
    except DomainValidationError as exc:
        raise HTTPException(status_code=409, detail=exc.message) from exc


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    body: ConversationCreate | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    try:
        conversation = ConversationService(db).create_conversation(current_user, body)
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    status_filter: ConversationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    items, next_cursor = ConversationService(db).list_conversations(
        current_user,
        status=status_filter,
        limit=limit,
        cursor=cursor,
        query=query,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    try:
        conversation = ConversationService(db).get_conversation(conversation_id, current_user)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return ConversationResponse.model_validate(conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: int,
    body: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    service = ConversationService(db)
    try:
        conversation = service.update_conversation(conversation_id, body, actor=current_user)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def list_messages(
    conversation_id: int,
    limit: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageResponse]:
    try:
        messages = ConversationService(db).list_messages(
            conversation_id, actor=current_user, limit=limit
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return [MessageResponse.model_validate(item) for item in messages]


@router.post(
    "/conversations/{conversation_id}/messages/{user_message_id}/select-answer",
    response_model=MessageResponse,
)
def select_answer(
    conversation_id: int,
    user_message_id: int,
    body: SelectAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service = ConversationService(db)
    try:
        user_message = service.select_answer(
            conversation_id,
            user_message_id,
            body.answer_id,
            actor=current_user,
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    except AgentMessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(user_message)
    return MessageResponse.model_validate(user_message)


@router.post(
    "/conversations/{conversation_id}/requests/{agent_request_id}/stop",
    response_model=AgentRequestStatusResponse,
)
def stop_agent_request(
    conversation_id: int,
    agent_request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentRequestStatusResponse:
    service = ConversationService(db)
    try:
        request = service.stop_request(conversation_id, agent_request_id, actor=current_user)
        assistant = (
            service.messages.get_by_id(request.assistant_message_id)
            if request.assistant_message_id
            else None
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    db.commit()
    return AgentRequestStatusResponse(
        id=request.id,
        conversation_id=request.conversation_id,
        client_request_id=request.client_request_id,
        status=request.status,
        user_message_id=request.user_message_id,
        assistant_message_id=request.assistant_message_id,
        cancel_requested=request.cancel_requested,
        error_code=request.error_code,
        assistant_status=assistant.status if assistant else None,
        assistant_content=assistant.content if assistant else None,
    )


@router.get(
    "/conversations/{conversation_id}/requests/{agent_request_id}",
    response_model=AgentRequestStatusResponse,
)
def get_agent_request(
    conversation_id: int,
    agent_request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentRequestStatusResponse:
    service = ConversationService(db)
    try:
        request, assistant = service.get_request_status(
            conversation_id, agent_request_id, actor=current_user
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    return AgentRequestStatusResponse(
        id=request.id,
        conversation_id=request.conversation_id,
        client_request_id=request.client_request_id,
        status=request.status,
        user_message_id=request.user_message_id,
        assistant_message_id=request.assistant_message_id,
        cancel_requested=request.cancel_requested,
        error_code=request.error_code,
        assistant_status=assistant.status if assistant else None,
        assistant_content=assistant.content if assistant else None,
    )


@router.get(
    "/conversations/{conversation_id}/active-generation",
    response_model=ActiveGenerationResponse,
)
def get_active_generation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ActiveGenerationResponse:
    """Return in-flight generation; also reclaims stale orphaned STREAMING slots."""
    service = ConversationService(db)
    try:
        request, assistant = service.get_active_generation(
            conversation_id, actor=current_user
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    db.commit()
    if request is None:
        return ActiveGenerationResponse(active=False, request=None)
    return ActiveGenerationResponse(
        active=True,
        request=AgentRequestStatusResponse(
            id=request.id,
            conversation_id=request.conversation_id,
            client_request_id=request.client_request_id,
            status=request.status,
            user_message_id=request.user_message_id,
            assistant_message_id=request.assistant_message_id,
            cancel_requested=request.cancel_requested,
            error_code=request.error_code,
            assistant_status=assistant.status if assistant else None,
            assistant_content=assistant.content if assistant else None,
        ),
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: int,
    body: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SendMessageResponse:
    service = ConversationService(db)
    try:
        conversation, user_msg, assistant_msg, tools_used, llm_used = await service.send_message(
            conversation_id, body, actor=current_user
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    except RequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except Exception:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="项目助手暂时无法完成回答，请稍后重试。",
        ) from None
    db.commit()
    db.refresh(conversation)
    db.refresh(user_msg)
    db.refresh(assistant_msg)
    return SendMessageResponse(
        conversation=ConversationResponse.model_validate(conversation),
        user_message=MessageResponse.model_validate(user_msg),
        assistant_message=MessageResponse.model_validate(assistant_msg),
        tools_used=tools_used,
        llm_used=llm_used,
    )


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: int,
    body: MessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """SSE stream: message_start / delta / tool_* / done / error."""
    service = ConversationService(db)
    try:
        conversation = service.get_conversation(conversation_id, current_user)
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    if conversation.status == ConversationStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send messages to an archived conversation",
        )

    assistant_id_box: dict[str, int | None] = {"id": None}

    async def event_gen() -> AsyncIterator[bytes]:
        try:
            async for event in service.stream_message(conversation_id, body, actor=current_user):
                if event.event == "message_start":
                    raw_id = event.data.get("message_id")
                    assistant_id_box["id"] = int(raw_id) if raw_id is not None else None
                yield encode_sse(event)
                if await request.is_disconnected():
                    break
        except RequestConflictError as exc:
            yield encode_sse(
                {
                    "event": "error",
                    "data": {"message": exc.message, "code": "REQUEST_CONFLICT"},
                }
            )
        except DomainValidationError as exc:
            yield encode_sse({"event": "error", "data": {"message": exc.message}})
        except ConversationNotFoundError:
            yield encode_sse({"event": "error", "data": {"message": "Conversation not found"}})
        except Exception:
            yield encode_sse(
                {
                    "event": "error",
                    "data": {"message": "项目助手暂时无法完成回答，请稍后重试。"},
                }
            )
        finally:
            aid = assistant_id_box["id"]
            if aid is not None and await request.is_disconnected():
                with contextlib.suppress(Exception):
                    service.finalize_streaming_message(aid, interrupted=True)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate/stream")
async def regenerate_message_stream(
    conversation_id: int,
    message_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    service = ConversationService(db)
    assistant_id_box: dict[str, int | None] = {"id": None}

    async def event_gen() -> AsyncIterator[bytes]:
        try:
            async for event in service.regenerate_stream(
                conversation_id, message_id, actor=current_user
            ):
                if event.event == "message_start":
                    raw_id = event.data.get("message_id")
                    assistant_id_box["id"] = int(raw_id) if raw_id is not None else None
                yield encode_sse(event)
                if await request.is_disconnected():
                    break
        except ConversationNotFoundError:
            yield encode_sse({"event": "error", "data": {"message": "Conversation not found"}})
        except DomainValidationError as exc:
            yield encode_sse({"event": "error", "data": {"message": exc.message}})
        except Exception:
            yield encode_sse(
                {
                    "event": "error",
                    "data": {"message": "项目助手暂时无法完成回答，请稍后重试。"},
                }
            )
        finally:
            aid = assistant_id_box["id"]
            if aid is not None and await request.is_disconnected():
                with contextlib.suppress(Exception):
                    service.finalize_streaming_message(aid, interrupted=True)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    body: AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgentChatResponse:
    """Backward-compatible single-shot chat; always persists into a conversation."""
    service = ConversationService(db)
    try:
        conversation, user_msg, assistant_msg, tools_used, llm_used = await service.chat_compat(
            actor=current_user,
            message=body.message,
            conversation_id=body.conversation_id,
        )
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    except Exception:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="项目助手暂时无法完成回答，请稍后重试。",
        ) from None
    db.commit()
    return AgentChatResponse(
        reply=assistant_msg.content,
        tools_used=tools_used,
        llm_used=llm_used,
        conversation_id=conversation.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
    )


# --- Memory (PHASE E) ---


@router.get("/memories", response_model=list[MemoryResponse])
def list_memories(
    active_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryResponse]:
    items = MemoryService(db).list_memories(current_user, active_only=active_only)
    return [MemoryResponse.model_validate(item) for item in items]


@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResponse:
    try:
        memory = MemoryService(db).create(current_user, body)
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.patch("/memories/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResponse:
    try:
        memory = MemoryService(db).update(memory_id, body, actor=current_user)
    except MemoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
        ) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc
    db.commit()
    db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        MemoryService(db).deactivate(memory_id, actor=current_user)
    except MemoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found"
        ) from exc
    db.commit()
