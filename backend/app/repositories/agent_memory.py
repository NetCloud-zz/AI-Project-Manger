"""Repositories for AgentMemory and AIRun."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.agent_memory import AgentMemory
from app.models.ai_run import AIRun, AIRunStatus, AIRunType


class AgentMemoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, memory_id: int) -> AgentMemory | None:
        return self.db.get(AgentMemory, memory_id)

    def list_for_user(
        self,
        user_id: int,
        *,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[AgentMemory]:
        stmt: Select[tuple[AgentMemory]] = (
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(AgentMemory.updated_at.desc())
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(AgentMemory.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def list_for_context(
        self,
        user_id: int,
        *,
        project_id: int | None = None,
        active_only: bool = True,
        limit: int = 20,
    ) -> list[AgentMemory]:
        """USER memories always; PROJECT memories only when project_id is set."""
        from app.models.agent_memory import MemoryScope
        from sqlalchemy import or_

        conditions = [AgentMemory.scope == MemoryScope.USER]
        if project_id is not None:
            conditions.append(
                (AgentMemory.scope == MemoryScope.PROJECT)
                & (AgentMemory.project_id == project_id)
            )
        stmt: Select[tuple[AgentMemory]] = (
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id, or_(*conditions))
            .order_by(AgentMemory.updated_at.desc())
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(AgentMemory.is_active.is_(True))
        return list(self.db.scalars(stmt).all())

    def add(self, memory: AgentMemory) -> AgentMemory:
        self.db.add(memory)
        self.db.flush()
        return memory

    def save(self, memory: AgentMemory) -> AgentMemory:
        self.db.add(memory)
        self.db.flush()
        return memory


class AIRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, run_id: int) -> AIRun | None:
        return self.db.get(AIRun, run_id)

    def add(self, run: AIRun) -> AIRun:
        self.db.add(run)
        self.db.flush()
        return run

    def save(self, run: AIRun) -> AIRun:
        self.db.add(run)
        self.db.flush()
        return run

    def latest_for_resource(
        self,
        *,
        resource_type: str,
        resource_id: str,
        run_type: AIRunType | None = None,
    ) -> AIRun | None:
        stmt = (
            select(AIRun)
            .where(
                AIRun.resource_type == resource_type,
                AIRun.resource_id == resource_id,
            )
            .order_by(AIRun.created_at.desc())
            .limit(1)
        )
        if run_type is not None:
            stmt = stmt.where(AIRun.run_type == run_type)
        return self.db.scalars(stmt).first()

    def list_for_resource(
        self,
        *,
        resource_type: str,
        resource_id: str,
        limit: int = 20,
    ) -> list[AIRun]:
        stmt = (
            select(AIRun)
            .where(
                AIRun.resource_type == resource_type,
                AIRun.resource_id == resource_id,
            )
            .order_by(AIRun.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
