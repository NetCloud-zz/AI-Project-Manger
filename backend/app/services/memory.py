"""Agent memory service — explicit user preferences only."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.agent_memory import AgentMemory, MemoryScope
from app.models.user import User
from app.repositories.agent_memory import AgentMemoryRepository
from app.schemas.agent_memory import MemoryCreate, MemoryUpdate
from app.services.exceptions import DomainValidationError, MemoryNotFoundError

# Dynamic business facts must not be stored as memory.
_FORBIDDEN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(due\s*date|target\s*date|截止日期|到期日|目标日|完成日期)",
        r"(ON_TRACK|AT_RISK|DELAYED|ACTIVE|COMPLETED|TODO|IN_PROGRESS)",
        r"(当前状态|风险等级|负责人是|进度为|完成度为|已经完成|任务已经)",
        r"(owner|assignee)\s*[:=]",
        r"(该任务|这个任务|项目由).{0,20}(截止|完成|负责)",
        r"截止日期是\s*\d{4}",
        r"由[\u4e00-\u9fff]{2,10}负责",
    )
]


def looks_like_business_fact(content: str) -> bool:
    text = content.strip()
    return any(pattern.search(text) for pattern in _FORBIDDEN_PATTERNS)


class MemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AgentMemoryRepository(db)

    def list_memories(
        self,
        actor: User,
        *,
        active_only: bool = True,
    ) -> list[AgentMemory]:
        return self.repo.list_for_user(actor.id, active_only=active_only)

    def active_contents(
        self,
        actor: User,
        *,
        project_id: int | None = None,
        limit: int = 20,
    ) -> list[str]:
        """Load USER-scoped memories plus PROJECT memories for the bound project only."""
        items = self.repo.list_for_context(
            actor.id, project_id=project_id, active_only=True, limit=limit
        )
        return [item.content for item in items if item.content.strip()]

    def create(self, actor: User, data: MemoryCreate) -> AgentMemory:
        content = data.content.strip()
        if not content:
            raise DomainValidationError("Memory content is required")
        if looks_like_business_fact(content):
            raise DomainValidationError(
                "不能将任务状态、截止日期、风险等级等动态业务事实保存为记忆；"
                "请保存偏好或关注重点，例如「汇报时优先说明风险与延期」。"
            )
        project_id: int | None = None
        if data.scope == MemoryScope.PROJECT:
            if data.project_id is None:
                raise DomainValidationError("PROJECT scope requires project_id")
            from app.core.permissions import can_view_project
            from app.models.project import Project

            project = self.db.get(Project, data.project_id)
            if project is None or not can_view_project(self.db, actor, project):
                raise DomainValidationError("无权为该项目创建记忆，或项目不存在")
            project_id = project.id
        memory = AgentMemory(
            user_id=actor.id,
            scope=data.scope,
            memory_type=data.memory_type,
            content=content[:2000],
            project_id=project_id,
            is_active=True,
        )
        return self.repo.add(memory)

    def update(self, memory_id: int, data: MemoryUpdate, *, actor: User) -> AgentMemory:
        memory = self._owned(memory_id, actor)
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            raise DomainValidationError("No memory fields to update")
        if "content" in updates and updates["content"] is not None:
            content = updates["content"].strip()
            if not content:
                raise DomainValidationError("Memory content is required")
            if looks_like_business_fact(content):
                raise DomainValidationError(
                    "不能将任务状态、截止日期、风险等级等动态业务事实保存为记忆。"
                )
            updates["content"] = content[:2000]
        for field, value in updates.items():
            setattr(memory, field, value)
        return self.repo.save(memory)

    def deactivate(self, memory_id: int, *, actor: User) -> AgentMemory:
        memory = self._owned(memory_id, actor)
        memory.is_active = False
        return self.repo.save(memory)

    def _owned(self, memory_id: int, actor: User) -> AgentMemory:
        memory = self.repo.get_by_id(memory_id)
        if memory is None or memory.user_id != actor.id:
            raise MemoryNotFoundError
        return memory
