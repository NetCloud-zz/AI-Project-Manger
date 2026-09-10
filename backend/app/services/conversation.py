"""Conversation persistence and chat orchestration for the Project Assistant."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.agents.context_builder import (
    AgentContextBuilder,
    ContextBudgetExceededError,
    should_refresh_summary,
)
from app.agents.management_agent import SYSTEM_PROMPT, ManagementAgent
from app.agents.stream_events import AgentStreamEvent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.permissions import can_view_project
from app.models.agent_conversation import (
    AgentConversation,
    AgentMessage,
    ConversationStatus,
    MessageRole,
    MessageStatus,
)
from app.models.agent_request import AgentRequest, AgentRequestStatus
from app.models.project import Project
from app.models.user import User
from app.repositories.agent_conversation import (
    AgentConversationRepository,
    AgentMessageRepository,
    touch_conversation,
)
from app.schemas.agent import ConversationCreate, ConversationUpdate, MessageCreate
from app.services.agent_idempotency import (
    begin_request,
    mark_request_finished,
    mark_request_running,
)
from app.services.answer_versions import (
    next_answer_version,
    resolve_parent_user_message,
    selected_context_messages,
)
from app.services.exceptions import (
    AgentMessageNotFoundError,
    ConversationNotFoundError,
    DomainValidationError,
)

logger = get_logger(__name__)


def title_from_message(content: str, *, max_len: int = 28) -> str:
    """Local title from the first user message — no extra LLM call."""
    text = " ".join(content.strip().split())
    if not text:
        return "新对话"
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.conversations = AgentConversationRepository(db)
        self.messages = AgentMessageRepository(db)

    def _owned(self, conversation_id: int, actor: User) -> AgentConversation:
        conversation = self.conversations.get_by_id(conversation_id)
        if conversation is None or conversation.user_id != actor.id:
            # Hide existence of other users' conversations.
            raise ConversationNotFoundError
        return conversation

    def _validate_project_binding(self, actor: User, project_id: int | None) -> int | None:
        if project_id is None:
            return None
        project = self.db.get(Project, project_id)
        if project is None or not can_view_project(self.db, actor, project):
            msg = "无权绑定该项目，或项目不存在"
            raise DomainValidationError(msg)
        return project.id

    def _bound_project_payload(
        self, actor: User, conversation: AgentConversation
    ) -> dict[str, object] | None:
        if conversation.project_id is None:
            return None
        project = self.db.get(Project, conversation.project_id)
        if project is None or not can_view_project(self.db, actor, project):
            # Binding became invalid — do not inject project content.
            return None
        return {
            "id": project.id,
            "code": project.project_code,
            "name": project.project_name,
        }

    def _assert_generation_slot(
        self,
        conversation_id: int,
        *,
        exclude_request_id: int | None = None,
    ) -> None:
        if self.messages.has_streaming(conversation_id):
            msg = "当前会话已有进行中的生成，请等待完成或先停止"
            raise DomainValidationError(msg)
        stmt = select(AgentRequest.id).where(
            AgentRequest.conversation_id == conversation_id,
            AgentRequest.status.in_((AgentRequestStatus.ACCEPTED, AgentRequestStatus.RUNNING)),
        )
        if exclude_request_id is not None:
            stmt = stmt.where(AgentRequest.id != exclude_request_id)
        active = self.db.scalar(stmt.limit(1))
        if active is not None:
            msg = "当前会话已有进行中的请求，请等待完成或先停止"
            raise DomainValidationError(msg)

    def create_conversation(
        self,
        actor: User,
        data: ConversationCreate | None = None,
    ) -> AgentConversation:
        data = data or ConversationCreate()
        title = (data.title or "").strip() or "新对话"
        project_id = self._validate_project_binding(actor, data.project_id)
        conversation = AgentConversation(
            user_id=actor.id,
            title=title[:200],
            status=ConversationStatus.ACTIVE,
            project_id=project_id,
        )
        return self.conversations.add(conversation)

    def list_conversations(
        self,
        actor: User,
        *,
        status: ConversationStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
        query: str | None = None,
    ) -> tuple[list[AgentConversation], str | None]:
        return self.conversations.list_for_user(
            actor.id, status=status, limit=limit, cursor=cursor, query=query
        )

    def get_conversation(self, conversation_id: int, actor: User) -> AgentConversation:
        return self._owned(conversation_id, actor)

    def update_conversation(
        self,
        conversation_id: int,
        data: ConversationUpdate,
        *,
        actor: User,
    ) -> AgentConversation:
        conversation = self._owned(conversation_id, actor)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            msg = "No conversation fields to update"
            raise DomainValidationError(msg)
        if "title" in updates and updates["title"] is not None:
            updates["title"] = updates["title"].strip()[:200]
        if "project_id" in updates:
            updates["project_id"] = self._validate_project_binding(actor, updates["project_id"])
        for field, value in updates.items():
            setattr(conversation, field, value)
        return self.conversations.save(conversation)

    def list_messages(
        self,
        conversation_id: int,
        *,
        actor: User,
        limit: int | None = None,
    ) -> list[AgentMessage]:
        self._owned(conversation_id, actor)
        return self.messages.list_for_conversation(conversation_id, limit=limit)

    def select_answer(
        self,
        conversation_id: int,
        user_message_id: int,
        answer_id: int,
        *,
        actor: User,
    ) -> AgentMessage:
        """Persist which answer version is active for a USER turn."""
        self._owned(conversation_id, actor)
        user_message = self.messages.get_by_id(user_message_id)
        if (
            user_message is None
            or user_message.conversation_id != conversation_id
            or user_message.role != MessageRole.USER
        ):
            raise AgentMessageNotFoundError
        answer = self.messages.get_by_id(answer_id)
        if (
            answer is None
            or answer.conversation_id != conversation_id
            or answer.role != MessageRole.ASSISTANT
            or answer.parent_user_message_id != user_message.id
        ):
            msg = "回答版本不属于该提问"
            raise DomainValidationError(msg)
        user_message.selected_answer_id = answer.id
        return self.messages.save(user_message)

    async def send_message(
        self,
        conversation_id: int,
        data: MessageCreate,
        *,
        actor: User,
    ) -> tuple[AgentConversation, AgentMessage, AgentMessage, list[str], bool]:
        """Persist user message, run ManagementAgent with multi-turn context, persist reply."""
        conversation = self._owned(conversation_id, actor)
        if conversation.status == ConversationStatus.ARCHIVED:
            msg = "Cannot send messages to an archived conversation"
            raise DomainValidationError(msg)

        agent_request, _ = begin_request(
            self.db,
            user_id=actor.id,
            conversation_id=conversation.id,
            client_request_id=str(uuid4()),
            content=data.content,
        )
        now = datetime.now(UTC)
        user_message = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data.content.strip(),
            status=MessageStatus.COMPLETED,
            completed_at=now,
        )
        self.messages.add(user_message)

        if (
            conversation.title in ("新对话", "")
            and self.messages.count_for_conversation(conversation.id) == 1
        ):
            conversation.title = title_from_message(user_message.content)

        touch_conversation(conversation, when=now)
        self.conversations.save(conversation)
        self.db.flush()

        assistant = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.PENDING,
            parent_user_message_id=user_message.id,
            answer_version=1,
            association_status="NORMAL",
        )
        self.messages.add(assistant)
        self.db.flush()
        user_message.selected_answer_id = assistant.id
        self.messages.save(user_message)
        agent_request.user_message_id = user_message.id
        agent_request.assistant_message_id = assistant.id
        agent_request.status = AgentRequestStatus.RUNNING
        # Commit conversation rows before tool execution so tool failures cannot
        # roll back the user/assistant messages (F16).
        self.db.commit()

        settings = get_settings()
        recent_limit = max(settings.AGENT_RECENT_MESSAGES, 1) + 2
        history = selected_context_messages(
            [
                msg
                for msg in self.messages.list_recent_for_context(
                    conversation.id,
                    limit=recent_limit,
                    through_id=user_message.id,
                )
                if msg.id != assistant.id
            ]
        )
        from app.services.memory import MemoryService

        try:
            user_memories = MemoryService(self.db).active_contents(
                actor, project_id=conversation.project_id
            )
            built = AgentContextBuilder(settings).build(
                system_prompt=SYSTEM_PROMPT,
                current_user_content=user_message.content,
                prior_messages=history,
                conversation_summary=conversation.summary,
                user_memories=user_memories,
                bound_project=self._bound_project_payload(actor, conversation),
            )
        except ContextBudgetExceededError as exc:
            assistant.content = str(exc)
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            raise DomainValidationError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            assistant.content = "项目助手暂时无法完成回答，请稍后重试。"
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            assistant.tool_results = [{"error": type(exc).__name__}]
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            raise

        try:
            result = await ManagementAgent(self.db, settings=settings).chat(
                user_message.content,
                actor=actor,
                context_messages=built.messages,
                allow_writes=True,
                agent_request_id=agent_request.id,
            )
            assistant.content = result.reply
            assistant.status = MessageStatus.COMPLETED
            assistant.completed_at = datetime.now(UTC)
            assistant.tool_calls = (
                [{"name": name} for name in result.tools_used] if result.tools_used else None
            )
            assistant.tool_results = list(result.tool_results) or (
                [{"name": name, "success": True} for name in result.tools_used]
                if result.tools_used
                else None
            )
            assistant.cards = list(result.cards) or None
            if result.llm_used:
                assistant.model = settings.LLM_MODEL_REASONING
            tools_used = list(result.tools_used)
            llm_used = result.llm_used
            agent_request.status = AgentRequestStatus.COMPLETED
            agent_request.completed_at = datetime.now(UTC)
        except Exception as exc:  # noqa: BLE001 — persist failure state for the UI
            assistant.content = "项目助手暂时无法完成回答，请稍后重试。"
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            assistant.tool_results = [{"error": type(exc).__name__}]
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            raise

        self.messages.save(assistant)
        touch_conversation(conversation, when=assistant.completed_at or datetime.now(UTC))
        self.conversations.save(conversation)

        self._maybe_enqueue_summary(conversation, assistant)
        return conversation, user_message, assistant, tools_used, llm_used

    async def stream_message(
        self,
        conversation_id: int,
        data: MessageCreate,
        *,
        actor: User,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Persist user + STREAMING assistant, then yield SSE agent events."""
        conversation = self._owned(conversation_id, actor)
        if conversation.status == ConversationStatus.ARCHIVED:
            msg = "Cannot send messages to an archived conversation"
            raise DomainValidationError(msg)

        agent_request: AgentRequest | None = None
        client_request_id = (data.client_request_id or "").strip() or str(uuid4())
        if client_request_id:
            agent_request, is_new = begin_request(
                self.db,
                user_id=actor.id,
                conversation_id=conversation.id,
                client_request_id=client_request_id,
                content=data.content,
            )
            if not is_new:
                async for event in self._replay_or_attach_request(agent_request, actor=actor):
                    yield event
                return
            self._assert_generation_slot(conversation.id, exclude_request_id=agent_request.id)
        else:
            self._assert_generation_slot(conversation.id)

        now = datetime.now(UTC)
        user_message = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=data.content.strip(),
            status=MessageStatus.COMPLETED,
            completed_at=now,
        )
        self.messages.add(user_message)

        if (
            conversation.title in ("新对话", "")
            and self.messages.count_for_conversation(conversation.id) == 1
        ):
            conversation.title = title_from_message(user_message.content)

        touch_conversation(conversation, when=now)
        self.conversations.save(conversation)
        self.db.flush()

        assistant = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            parent_user_message_id=user_message.id,
            answer_version=1,
            association_status="NORMAL",
        )
        self.messages.add(assistant)
        self.db.flush()
        user_message.selected_answer_id = assistant.id
        self.messages.save(user_message)

        if agent_request is not None:
            mark_request_running(self.db, agent_request)
            agent_request.user_message_id = user_message.id
            agent_request.assistant_message_id = assistant.id
            self.db.add(agent_request)

        self.db.commit()

        yield AgentStreamEvent(
            event="message_start",
            data={
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "message_id": assistant.id,
                "client_request_id": client_request_id,
                "agent_request_id": agent_request.id if agent_request else None,
                "answer_version": 1,
                "parent_user_message_id": user_message.id,
            },
        )

        async for event in self._run_assistant_stream(
            conversation=conversation,
            user_message=user_message,
            assistant=assistant,
            actor=actor,
            history_cutoff_inclusive=user_message.id,
            allow_writes=True,
            agent_request=agent_request,
        ):
            yield event

    async def regenerate_stream(
        self,
        conversation_id: int,
        assistant_message_id: int,
        *,
        actor: User,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Re-answer the preceding user message (read-only tools by default)."""
        conversation = self._owned(conversation_id, actor)
        if conversation.status == ConversationStatus.ARCHIVED:
            msg = "Cannot regenerate in an archived conversation"
            raise DomainValidationError(msg)

        messages = self.messages.list_for_conversation(conversation_id)
        target = next((m for m in messages if m.id == assistant_message_id), None)
        if target is None or target.role != MessageRole.ASSISTANT:
            raise ConversationNotFoundError

        user_message = resolve_parent_user_message(messages, target)
        if user_message is None:
            msg = "No user message to regenerate from"
            raise DomainValidationError(msg)

        # Persist association for legacy targets so subsequent regenerations stay fixed.
        if target.parent_user_message_id is None:
            target.parent_user_message_id = user_message.id
            target.answer_version = target.answer_version or 1
            target.association_status = "NORMAL"
            self.messages.save(target)

        if (
            target.status
            in (
                MessageStatus.STREAMING,
                MessageStatus.PENDING,
                MessageStatus.FAILED,
            )
            and target.status != MessageStatus.FAILED
        ):
            target.status = MessageStatus.FAILED
            target.completed_at = datetime.now(UTC)
            self.messages.save(target)

        self._assert_generation_slot(conversation.id)

        version = next_answer_version(messages, user_message.id)
        assistant = AgentMessage(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            parent_user_message_id=user_message.id,
            regenerated_from_id=target.id,
            answer_version=version,
            association_status="NORMAL",
        )
        self.messages.add(assistant)
        self.db.flush()
        user_message.selected_answer_id = assistant.id
        self.messages.save(user_message)
        touch_conversation(conversation, when=datetime.now(UTC))
        self.conversations.save(conversation)
        self.db.commit()

        yield AgentStreamEvent(
            event="message_start",
            data={
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "message_id": assistant.id,
                "regenerated_from": target.id,
                "allow_writes": False,
                "answer_version": version,
                "parent_user_message_id": user_message.id,
            },
        )

        async for event in self._run_assistant_stream(
            conversation=conversation,
            user_message=user_message,
            assistant=assistant,
            actor=actor,
            history_cutoff_inclusive=user_message.id,
            allow_writes=False,
            agent_request=None,
        ):
            yield event

    async def _replay_or_attach_request(
        self,
        agent_request: AgentRequest,
        *,
        actor: User,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Return stored outcome for a duplicate client_request_id."""
        if agent_request.status == AgentRequestStatus.COMPLETED:
            assistant = (
                self.messages.get_by_id(agent_request.assistant_message_id)
                if agent_request.assistant_message_id
                else None
            )
            user_message_id = agent_request.user_message_id
            if assistant is None or user_message_id is None:
                msg = "幂等请求缺少已保存的消息"
                raise DomainValidationError(msg)
            yield AgentStreamEvent(
                event="message_start",
                data={
                    "conversation_id": agent_request.conversation_id,
                    "user_message_id": user_message_id,
                    "message_id": assistant.id,
                    "client_request_id": agent_request.client_request_id,
                    "agent_request_id": agent_request.id,
                    "idempotent_replay": True,
                },
            )
            if assistant.content:
                yield AgentStreamEvent(event="delta", data={"content": assistant.content})
            for card in assistant.cards or []:
                yield AgentStreamEvent(event="card", data=card)
            tools = []
            if assistant.tool_calls:
                tools = [
                    str(item.get("name"))
                    for item in assistant.tool_calls
                    if isinstance(item, dict) and item.get("name")
                ]
            yield AgentStreamEvent(
                event="done",
                data={
                    "message_id": assistant.id,
                    "conversation_id": agent_request.conversation_id,
                    "tools_used": tools,
                    "tool_results": assistant.tool_results or [],
                    "cards": assistant.cards or [],
                    "llm_used": bool(assistant.model),
                    "idempotent_replay": True,
                },
            )
            return

        if agent_request.status in {
            AgentRequestStatus.ACCEPTED,
            AgentRequestStatus.RUNNING,
        }:
            # Concurrent duplicate while the first attempt is still running.
            yield AgentStreamEvent(
                event="message_start",
                data={
                    "conversation_id": agent_request.conversation_id,
                    "user_message_id": agent_request.user_message_id,
                    "message_id": agent_request.assistant_message_id,
                    "client_request_id": agent_request.client_request_id,
                    "agent_request_id": agent_request.id,
                    "idempotent_replay": True,
                    "status": agent_request.status.value,
                },
            )
            yield AgentStreamEvent(
                event="done",
                data={
                    "message_id": agent_request.assistant_message_id,
                    "conversation_id": agent_request.conversation_id,
                    "tools_used": [],
                    "tool_results": [],
                    "cards": [],
                    "llm_used": False,
                    "idempotent_replay": True,
                    "status": agent_request.status.value,
                },
            )
            return

        # FAILED: allow a fresh attempt would need a new client_request_id; surface error.
        yield AgentStreamEvent(
            event="error",
            data={"message": "该请求此前已失败，请使用新的 client_request_id 重试"},
        )

    async def _run_assistant_stream(
        self,
        *,
        conversation: AgentConversation,
        user_message: AgentMessage,
        assistant: AgentMessage,
        actor: User,
        history_cutoff_inclusive: int,
        allow_writes: bool = True,
        agent_request: AgentRequest | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        settings = get_settings()
        content_parts: list[str] = []
        tools_used: list[str] = []
        tool_results: list[dict[str, object]] = []
        cards: list[dict[str, object]] = []
        llm_used = settings.llm_configured
        client_aborted = False
        stopped_by_user = False
        request_id = agent_request.id if agent_request is not None else None

        try:
            recent_limit = max(settings.AGENT_RECENT_MESSAGES, 1) + 2
            history = selected_context_messages(
                self.messages.list_recent_for_context(
                    conversation.id,
                    limit=recent_limit,
                    through_id=history_cutoff_inclusive,
                )
            )
            from app.services.memory import MemoryService

            user_memories = MemoryService(self.db).active_contents(
                actor, project_id=conversation.project_id
            )
            built = AgentContextBuilder(settings).build(
                system_prompt=SYSTEM_PROMPT,
                current_user_content=user_message.content,
                prior_messages=history,
                conversation_summary=conversation.summary,
                user_memories=user_memories,
                bound_project=self._bound_project_payload(actor, conversation),
            )
        except ContextBudgetExceededError as exc:
            assistant.content = str(exc)
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            if agent_request is not None:
                mark_request_finished(
                    self.db,
                    agent_request,
                    status=AgentRequestStatus.FAILED,
                    user_message_id=user_message.id,
                    assistant_message_id=assistant.id,
                    error_code="CONTEXT_BUDGET_EXCEEDED",
                )
            self.db.commit()
            yield AgentStreamEvent(event="error", data={"message": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 — F07: context prep failures get a terminal status
            logger.exception(
                "agent.conversation.context_prepare_failed",
                conversation_id=conversation.id,
                assistant_id=assistant.id,
            )
            assistant.content = "项目助手暂时无法完成回答，请稍后重试。"
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            assistant.tool_results = [{"error": type(exc).__name__}]
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            if agent_request is not None:
                mark_request_finished(
                    self.db,
                    agent_request,
                    status=AgentRequestStatus.FAILED,
                    user_message_id=user_message.id,
                    assistant_message_id=assistant.id,
                    error_code=type(exc).__name__,
                )
            self.db.commit()
            yield AgentStreamEvent(
                event="error",
                data={"message": "项目助手暂时无法完成回答，请稍后重试。"},
            )
            return

        try:
            async for event in ManagementAgent(self.db, settings=settings).chat_stream(
                user_message.content,
                actor=actor,
                context_messages=built.messages,
                allow_writes=allow_writes,
                agent_request_id=request_id,
            ):
                if request_id is not None and self._is_cancel_requested(request_id):
                    stopped_by_user = True
                    break
                if event.event == "delta":
                    piece = str(event.data.get("content") or "")
                    if piece:
                        content_parts.append(piece)
                        assistant.content = "".join(content_parts)
                elif event.event == "tool_start":
                    name = str(event.data.get("tool") or "")
                    if name:
                        tools_used.append(name)
                    if request_id is not None:
                        self._touch_request_heartbeat(request_id)
                elif event.event == "tool_end":
                    record: dict[str, object] = {
                        "name": event.data.get("tool"),
                        "success": bool(event.data.get("success", True)),
                    }
                    if event.data.get("tool_call_id") is not None:
                        record["tool_call_id"] = event.data.get("tool_call_id")
                    if event.data.get("operation_id") is not None:
                        record["operation_id"] = event.data.get("operation_id")
                    if event.data.get("error_code") is not None:
                        record["error_code"] = event.data.get("error_code")
                        record["error_message"] = event.data.get("error_message")
                        record["retryable"] = event.data.get("retryable")
                    tool_results.append(record)
                elif event.event == "card":
                    if event.data.get("type") == "execution_plan":
                        cards = [card for card in cards if not (card.get("type") == "execution_plan" and card.get("request_id") == event.data.get("request_id"))]
                    cards.append(dict(event.data))
                yield event
        except GeneratorExit:
            client_aborted = True
            raise
        except Exception as exc:  # noqa: BLE001 — persist failure + surface error event
            logger.exception(
                "agent.conversation.stream_failed",
                conversation_id=conversation.id,
                assistant_id=assistant.id,
            )
            assistant.content = "".join(content_parts) or "项目助手暂时无法完成回答，请稍后重试。"
            assistant.status = MessageStatus.FAILED
            assistant.completed_at = datetime.now(UTC)
            assistant.tool_calls = (
                [{"name": name} for name in dict.fromkeys(tools_used)] if tools_used else None
            )
            assistant.tool_results = tool_results or [{"error": type(exc).__name__}]
            assistant.cards = cards or None
            self.messages.save(assistant)
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
            if agent_request is not None:
                mark_request_finished(
                    self.db,
                    agent_request,
                    status=AgentRequestStatus.FAILED,
                    user_message_id=user_message.id,
                    assistant_message_id=assistant.id,
                    error_code=type(exc).__name__,
                )
            self.db.commit()
            yield AgentStreamEvent(
                event="error",
                data={"message": "项目助手暂时无法完成回答，请稍后重试。"},
            )
            return
        finally:
            if client_aborted and assistant.status == MessageStatus.STREAMING:
                self._persist_stream_terminal(
                    conversation=conversation,
                    assistant=assistant,
                    user_message=user_message,
                    agent_request=agent_request,
                    content="".join(content_parts),
                    tools_used=tools_used,
                    tool_results=tool_results,
                    cards=cards,
                    llm_used=llm_used,
                    message_status=MessageStatus.INTERRUPTED,
                    request_status=AgentRequestStatus.INTERRUPTED,
                )

        # Another session may have force-finalized (page leave / stop). Refresh first.
        self.db.refresh(assistant)
        if agent_request is not None:
            self.db.refresh(agent_request)
            if agent_request.cancel_requested:
                stopped_by_user = True

        if stopped_by_user:
            if assistant.status == MessageStatus.STREAMING:
                self._persist_stream_terminal(
                    conversation=conversation,
                    assistant=assistant,
                    user_message=user_message,
                    agent_request=agent_request,
                    content="".join(content_parts),
                    tools_used=tools_used,
                    tool_results=tool_results,
                    cards=cards,
                    llm_used=llm_used,
                    message_status=MessageStatus.STOPPED,
                    request_status=AgentRequestStatus.STOPPED,
                )
            yield AgentStreamEvent(
                event="done",
                data={
                    "message_id": assistant.id,
                    "conversation_id": conversation.id,
                    "tools_used": list(dict.fromkeys(tools_used)),
                    "tool_results": tool_results,
                    "cards": cards,
                    "llm_used": llm_used,
                    "status": MessageStatus.STOPPED.value,
                    "client_request_id": agent_request.client_request_id if agent_request else None,
                    "agent_request_id": agent_request.id if agent_request else None,
                },
            )
            return

        if assistant.status != MessageStatus.STREAMING:
            return

        assistant.content = "".join(content_parts)
        assistant.status = MessageStatus.COMPLETED
        assistant.completed_at = datetime.now(UTC)
        assistant.tool_calls = (
            [{"name": name} for name in dict.fromkeys(tools_used)] if tools_used else None
        )
        assistant.tool_results = tool_results or None
        assistant.cards = cards or None
        if llm_used:
            assistant.model = settings.LLM_MODEL_REASONING
        self.messages.save(assistant)
        touch_conversation(conversation, when=assistant.completed_at)
        self.conversations.save(conversation)
        if agent_request is not None:
            mark_request_finished(
                self.db,
                agent_request,
                status=AgentRequestStatus.COMPLETED,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
            )
        self.db.commit()
        self._maybe_enqueue_summary(conversation, assistant)

        yield AgentStreamEvent(
            event="done",
            data={
                "message_id": assistant.id,
                "conversation_id": conversation.id,
                "tools_used": list(dict.fromkeys(tools_used)),
                "tool_results": tool_results,
                "cards": cards,
                "llm_used": llm_used,
                "client_request_id": agent_request.client_request_id if agent_request else None,
                "agent_request_id": agent_request.id if agent_request else None,
            },
        )

    def _is_cancel_requested(self, request_id: int) -> bool:
        row = self.db.get(AgentRequest, request_id)
        return bool(row and row.cancel_requested)

    def _touch_request_heartbeat(self, request_id: int) -> None:
        row = self.db.get(AgentRequest, request_id)
        if row is None:
            return
        row.heartbeat_at = datetime.now(UTC)
        self.db.add(row)
        self.db.flush()

    def _persist_stream_terminal(
        self,
        *,
        conversation: AgentConversation,
        assistant: AgentMessage,
        user_message: AgentMessage,
        agent_request: AgentRequest | None,
        content: str,
        tools_used: list[str],
        tool_results: list[dict[str, object]],
        cards: list[dict[str, object]],
        llm_used: bool,
        message_status: MessageStatus,
        request_status: AgentRequestStatus,
    ) -> None:
        settings = get_settings()
        assistant.content = content
        assistant.status = message_status
        assistant.completed_at = datetime.now(UTC)
        assistant.tool_calls = (
            [{"name": name} for name in dict.fromkeys(tools_used)] if tools_used else None
        )
        assistant.tool_results = tool_results or None
        assistant.cards = cards or None
        if llm_used and content:
            assistant.model = settings.LLM_MODEL_REASONING
        self.messages.save(assistant)
        touch_conversation(conversation, when=datetime.now(UTC))
        self.conversations.save(conversation)
        if agent_request is not None:
            mark_request_finished(
                self.db,
                agent_request,
                status=request_status,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
            )
        self.db.commit()

    def finalize_streaming_message(
        self,
        assistant_message_id: int,
        *,
        stopped: bool = False,
        interrupted: bool = False,
    ) -> None:
        """Best-effort persist when the HTTP client disconnects or user stops."""
        assistant = self.messages.get_by_id(assistant_message_id)
        if assistant is None or assistant.status != MessageStatus.STREAMING:
            return
        if stopped:
            assistant.status = MessageStatus.STOPPED
        elif interrupted:
            assistant.status = MessageStatus.INTERRUPTED
        else:
            assistant.status = MessageStatus.INTERRUPTED
        assistant.completed_at = datetime.now(UTC)
        if not (assistant.content or "").strip() and assistant.status == MessageStatus.FAILED:
            assistant.content = "项目助手暂时无法完成回答，请稍后重试。"
        self.messages.save(assistant)
        conversation = self.conversations.get_by_id(assistant.conversation_id)
        if conversation is not None:
            touch_conversation(conversation, when=datetime.now(UTC))
            self.conversations.save(conversation)
        request = self.db.scalar(
            select(AgentRequest).where(AgentRequest.assistant_message_id == assistant.id)
        )
        if request is not None and request.status in {
            AgentRequestStatus.ACCEPTED,
            AgentRequestStatus.RUNNING,
        }:
            mark_request_finished(
                self.db,
                request,
                status=(AgentRequestStatus.STOPPED if stopped else AgentRequestStatus.INTERRUPTED),
                user_message_id=request.user_message_id,
                assistant_message_id=assistant.id,
            )
        self.db.commit()

    def stop_request(
        self,
        conversation_id: int,
        agent_request_id: int,
        *,
        actor: User,
        force_finalize: bool = True,
    ) -> AgentRequest:
        """Cancel generation. Optionally finalize STREAMING so the slot unlocks.

        When the browser left the page, the SSE loop may already be dead and never
        observe ``cancel_requested``. Force-finalize releases the generation lock.
        """
        self._owned(conversation_id, actor)
        request = self.db.get(AgentRequest, agent_request_id)
        if (
            request is None
            or request.conversation_id != conversation_id
            or request.user_id != actor.id
        ):
            raise ConversationNotFoundError
        if request.status in {
            AgentRequestStatus.COMPLETED,
            AgentRequestStatus.FAILED,
            AgentRequestStatus.STOPPED,
            AgentRequestStatus.INTERRUPTED,
        }:
            return request
        request.cancel_requested = True
        request.heartbeat_at = datetime.now(UTC)
        self.db.add(request)
        self.db.flush()
        if not force_finalize:
            return request
        # Commit cancel flag first so a still-running stream loop can see it.
        self.db.commit()
        if request.assistant_message_id is not None:
            self.finalize_streaming_message(
                request.assistant_message_id,
                stopped=True,
                interrupted=False,
            )
        refreshed = self.db.get(AgentRequest, agent_request_id)
        if refreshed is not None and refreshed.status in {
            AgentRequestStatus.ACCEPTED,
            AgentRequestStatus.RUNNING,
        }:
            # No STREAMING row (or already finalized elsewhere) — still unlock slot.
            mark_request_finished(
                self.db,
                refreshed,
                status=AgentRequestStatus.STOPPED,
                user_message_id=refreshed.user_message_id,
                assistant_message_id=refreshed.assistant_message_id,
            )
            self.db.commit()
        return refreshed or request

    def get_active_generation(
        self,
        conversation_id: int,
        *,
        actor: User,
        stale_after_seconds: int = 180,
    ) -> tuple[AgentRequest | None, AgentMessage | None]:
        """Return the in-flight request/message, reclaiming orphans if needed."""
        self._owned(conversation_id, actor)
        self.reclaim_stale_generations(
            conversation_id, stale_after_seconds=stale_after_seconds
        )
        request = self.db.scalar(
            select(AgentRequest)
            .where(
                AgentRequest.conversation_id == conversation_id,
                AgentRequest.user_id == actor.id,
                AgentRequest.status.in_(
                    (AgentRequestStatus.ACCEPTED, AgentRequestStatus.RUNNING)
                ),
            )
            .order_by(AgentRequest.id.desc())
            .limit(1)
        )
        assistant: AgentMessage | None = None
        if request is None:
            assistant = self.db.scalar(
                select(AgentMessage)
                .where(
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.status == MessageStatus.STREAMING,
                )
                .order_by(AgentMessage.id.desc())
                .limit(1)
            )
            if assistant is not None:
                # Orphan STREAMING row without a live request — unlock.
                self.finalize_streaming_message(assistant.id, interrupted=True)
                return None, self.messages.get_by_id(assistant.id)
            return None, None
        if request.assistant_message_id is not None:
            assistant = self.messages.get_by_id(request.assistant_message_id)
        return request, assistant

    def reclaim_stale_generations(
        self,
        conversation_id: int,
        *,
        stale_after_seconds: int = 180,
    ) -> int:
        """Mark abandoned STREAMING/RUNNING generations as INTERRUPTED."""
        cutoff = datetime.now(UTC) - timedelta(seconds=max(30, stale_after_seconds))
        reclaimed = 0
        stale_requests = list(
            self.db.scalars(
                select(AgentRequest).where(
                    AgentRequest.conversation_id == conversation_id,
                    AgentRequest.status.in_(
                        (AgentRequestStatus.ACCEPTED, AgentRequestStatus.RUNNING)
                    ),
                    or_(
                        AgentRequest.heartbeat_at < cutoff,
                        and_(
                            AgentRequest.heartbeat_at.is_(None),
                            AgentRequest.created_at < cutoff,
                        ),
                    ),
                )
            )
        )
        for request in stale_requests:
            if request.assistant_message_id is not None:
                self.finalize_streaming_message(
                    request.assistant_message_id, interrupted=True
                )
            else:
                mark_request_finished(
                    self.db,
                    request,
                    status=AgentRequestStatus.INTERRUPTED,
                    user_message_id=request.user_message_id,
                    assistant_message_id=None,
                )
                self.db.commit()
            reclaimed += 1
        # STREAMING messages with no heartbeat (or very old created_at).
        streaming = list(
            self.db.scalars(
                select(AgentMessage).where(
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.status == MessageStatus.STREAMING,
                    AgentMessage.created_at < cutoff,
                )
            )
        )
        for assistant in streaming:
            self.finalize_streaming_message(assistant.id, interrupted=True)
            reclaimed += 1
        return reclaimed

    def get_request_status(
        self,
        conversation_id: int,
        agent_request_id: int,
        *,
        actor: User,
    ) -> tuple[AgentRequest, AgentMessage | None]:
        self._owned(conversation_id, actor)
        request = self.db.get(AgentRequest, agent_request_id)
        if (
            request is None
            or request.conversation_id != conversation_id
            or request.user_id != actor.id
        ):
            raise ConversationNotFoundError
        assistant = (
            self.messages.get_by_id(request.assistant_message_id)
            if request.assistant_message_id
            else None
        )
        return request, assistant

    def _maybe_enqueue_summary(
        self,
        conversation: AgentConversation,
        assistant: AgentMessage,
    ) -> None:
        settings = get_settings()
        message_count = self.messages.count_for_conversation(conversation.id)
        through = conversation.summary_through_message_id or conversation.summary_message_id
        since = self.messages.count_after_id(conversation.id, through)
        if should_refresh_summary(
            message_count=message_count,
            trigger=settings.AGENT_SUMMARY_TRIGGER_MESSAGES,
            summary_through_message_id=through,
            messages_since_summary=since,
        ):
            from app.workers.tasks import enqueue_conversation_summary

            enqueue_conversation_summary(conversation.id)

    async def chat_compat(
        self,
        *,
        actor: User,
        message: str,
        conversation_id: int | None = None,
    ) -> tuple[AgentConversation, AgentMessage, AgentMessage, list[str], bool]:
        """Legacy `/chat` helper: reuse or create a conversation, then send."""
        if conversation_id is not None:
            conversation = self._owned(conversation_id, actor)
        else:
            conversation = self.create_conversation(actor, ConversationCreate())
        return await self.send_message(conversation.id, MessageCreate(content=message), actor=actor)

    async def refresh_summary(self, conversation_id: int) -> AgentConversation | None:
        """Generate rolling summary with the Fast model. Called from worker."""
        from app.agents.conversation_summarizer import ConversationSummarizer
        from app.llm.base import LLMError

        conversation = self.conversations.get_by_id(conversation_id)
        if conversation is None:
            return None

        messages = self.messages.list_for_conversation(conversation_id)
        completed = [
            msg
            for msg in messages
            if msg.role in (MessageRole.USER, MessageRole.ASSISTANT)
            and msg.status == MessageStatus.COMPLETED
            and (msg.content or "").strip()
        ]
        if not completed:
            return conversation

        settings = get_settings()
        through = conversation.summary_through_message_id or conversation.summary_message_id
        # Incremental: only summarize messages not yet covered by the previous summary.
        if through is not None:
            older = [msg for msg in completed if msg.id > through]
        else:
            keep_recent = max(0, settings.AGENT_RECENT_MESSAGES)
            if keep_recent and len(completed) > keep_recent:
                older = completed[:-keep_recent]
            else:
                older = completed
        if not older:
            return conversation

        try:
            summary = await ConversationSummarizer(settings=settings).summarize(older)
        except LLMError as exc:
            logger.warning(
                "agent.conversation_summary.skipped",
                conversation_id=conversation_id,
                error=str(exc),
            )
            return conversation

        if conversation.summary and through is not None:
            conversation.summary = f"{conversation.summary.strip()}\n\n{summary.strip()}"
        else:
            conversation.summary = summary
        conversation.summary_updated_at = datetime.now(UTC)
        conversation.summary_message_id = older[-1].id
        conversation.summary_through_message_id = older[-1].id
        return self.conversations.save(conversation)
