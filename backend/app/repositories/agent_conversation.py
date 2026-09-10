"""Agent conversation data access."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.agent_conversation import (
    AgentConversation,
    AgentMessage,
    ConversationStatus,
    MessageStatus,
)


class AgentConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, conversation_id: int) -> AgentConversation | None:
        return self.db.get(AgentConversation, conversation_id)

    def list_for_user(
        self,
        user_id: int,
        *,
        status: ConversationStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
        query: str | None = None,
    ) -> tuple[list[AgentConversation], str | None]:
        """Return (items, next_cursor). Cursor is opaque conversation id for stable paging."""
        page_size = max(1, min(limit, 100))
        stmt = select(AgentConversation).where(AgentConversation.user_id == user_id)
        if status is not None:
            stmt = stmt.where(AgentConversation.status == status)
        needle = (query or "").strip()
        if needle:
            pattern = f"%{needle}%"
            message_match = (
                select(AgentMessage.conversation_id)
                .where(
                    AgentMessage.conversation_id == AgentConversation.id,
                    AgentMessage.content.like(pattern),
                )
                .correlate(AgentConversation)
                .exists()
            )
            stmt = stmt.where(
                or_(
                    AgentConversation.title.like(pattern),
                    message_match,
                )
            )
        if cursor:
            try:
                cursor_id = int(cursor)
            except ValueError:
                cursor_id = 0
            if cursor_id > 0:
                cursor_row = self.get_by_id(cursor_id)
                if cursor_row is not None and cursor_row.user_id == user_id:
                    last_at = cursor_row.last_message_at
                    if last_at is None:
                        stmt = stmt.where(AgentConversation.id < cursor_id)
                    else:
                        stmt = stmt.where(
                            or_(
                                AgentConversation.last_message_at < last_at,
                                (
                                    (AgentConversation.last_message_at == last_at)
                                    & (AgentConversation.id < cursor_id)
                                ),
                                AgentConversation.last_message_at.is_(None),
                            )
                        )
        stmt = stmt.order_by(
            desc(AgentConversation.last_message_at).nullslast(),
            desc(AgentConversation.id),
        ).limit(page_size + 1)
        rows = list(self.db.scalars(stmt).all())
        next_cursor: str | None = None
        if len(rows) > page_size:
            rows = rows[:page_size]
            next_cursor = str(rows[-1].id)
        return rows, next_cursor

    def add(self, conversation: AgentConversation) -> AgentConversation:
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def save(self, conversation: AgentConversation) -> AgentConversation:
        self.db.add(conversation)
        self.db.flush()
        return conversation


class AgentMessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, message_id: int) -> AgentMessage | None:
        return self.db.get(AgentMessage, message_id)

    def list_for_conversation(
        self,
        conversation_id: int,
        *,
        limit: int | None = None,
        before_id: int | None = None,
    ) -> list[AgentMessage]:
        if before_id is not None:
            stmt = (
                select(AgentMessage)
                .where(
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.id < before_id,
                )
                .order_by(AgentMessage.id.desc())
            )
            if limit is not None:
                stmt = stmt.limit(max(1, limit))
            rows = list(self.db.scalars(stmt).all())
            rows.reverse()
            return rows
        if limit is not None:
            # Fetch latest N then restore chronological order (OPT-08: DB-side limit).
            stmt = (
                select(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
                .order_by(AgentMessage.id.desc())
                .limit(max(1, limit))
            )
            rows = list(self.db.scalars(stmt).all())
            rows.reverse()
            return rows
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
            .order_by(AgentMessage.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_recent_for_context(
        self,
        conversation_id: int,
        *,
        limit: int,
        through_id: int | None = None,
    ) -> list[AgentMessage]:
        """Load at most ``limit`` messages ending at ``through_id`` (inclusive)."""
        stmt = select(AgentMessage).where(AgentMessage.conversation_id == conversation_id)
        if through_id is not None:
            stmt = stmt.where(AgentMessage.id <= through_id)
        stmt = stmt.order_by(AgentMessage.id.desc()).limit(max(1, limit))
        rows = list(self.db.scalars(stmt).all())
        rows.reverse()
        return rows

    def count_after_id(self, conversation_id: int, after_id: int | None) -> int:
        stmt = (
            select(func.count())
            .select_from(AgentMessage)
            .where(AgentMessage.conversation_id == conversation_id)
        )
        if after_id is not None:
            stmt = stmt.where(AgentMessage.id > after_id)
        return int(self.db.scalar(stmt) or 0)

    def has_streaming(self, conversation_id: int) -> bool:
        return (
            self.db.scalar(
                select(AgentMessage.id)
                .where(
                    AgentMessage.conversation_id == conversation_id,
                    AgentMessage.status == MessageStatus.STREAMING,
                )
                .limit(1)
            )
            is not None
        )

    def add(self, message: AgentMessage) -> AgentMessage:
        self.db.add(message)
        self.db.flush()
        return message

    def save(self, message: AgentMessage) -> AgentMessage:
        self.db.add(message)
        self.db.flush()
        return message

    def count_for_conversation(self, conversation_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(AgentMessage)
                .where(AgentMessage.conversation_id == conversation_id)
            )
            or 0
        )


def touch_conversation(conversation: AgentConversation, *, when: datetime) -> None:
    conversation.last_message_at = when
