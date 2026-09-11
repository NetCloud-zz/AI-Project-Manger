"""SQLAlchemy ORM models."""

from __future__ import annotations

from app.models.action_item import ActionItem, ActionItemPriority, ActionItemStatus
from app.models.advice_record import AdviceOutcome, AdviceRecord, AdviceStatus
from app.models.agent_conversation import (
    AgentConversation,
    AgentMessage,
    ConversationStatus,
    MessageRole,
    MessageStatus,
)
from app.models.agent_memory import AgentMemory, MemoryScope, MemoryType
from app.models.agent_batch import AgentBatchItem, AgentBatchOperation
from app.models.agent_command import AgentCommandItem, AgentCommandPlan
from app.models.agent_request import (
    AgentOperation,
    AgentOperationStatus,
    AgentRequest,
    AgentRequestStatus,
)
from app.models.agent_tool_call import AgentToolCall
from app.models.ai_run import AIRun, AIRunStatus, AIRunType
from app.models.audit_log import AuditLog
from app.models.change_proposal import ChangeProposal
from app.models.notification import NotificationEvent
from app.models.daily_project_summary import DailyProjectSummary
from app.models.issue import Issue, IssueSeverity, IssueStatus
from app.models.plan_draft import PlanDraft
from app.models.planning import (
    BranchGroup,
    BranchOption,
    Milestone,
    PlanVersion,
    ProjectMember,
    TaskGroup,
    TaskParticipant,
    WorkCalendar,
)
from app.models.progress_update import ProgressUpdate
from app.models.project import Project, ProjectRiskLevel, ProjectStatus
from app.models.risk_event import (
    RiskEvent,
    RiskEventLevel,
    RiskEventStatus,
    RiskEventType,
)
from app.models.task import Task, TaskAiStatus, TaskLink, TaskLinkType, TaskStatus
from app.models.user import User, UserRole, UserStatus

__all__ = [
    "AgentBatchItem",
    "AgentBatchOperation",
    "AgentCommandItem",
    "AgentCommandPlan",
    "ChangeProposal",
    "PlanDraft",
    "NotificationEvent",
    "ProjectMember",
    "TaskParticipant",
    "WorkCalendar",
    "Milestone",
    "TaskGroup",
    "BranchGroup",
    "BranchOption",
    "PlanVersion",
    "ActionItem",
    "ActionItemPriority",
    "ActionItemStatus",
    "AdviceOutcome",
    "AdviceRecord",
    "AdviceStatus",
    "RiskEvent",
    "RiskEventLevel",
    "RiskEventStatus",
    "RiskEventType",
    "AgentConversation",
    "AgentMemory",
    "AgentMessage",
    "AgentOperation",
    "AgentOperationStatus",
    "AgentRequest",
    "AgentRequestStatus",
    "AgentToolCall",
    "AIRun",
    "AIRunStatus",
    "AIRunType",
    "AuditLog",
    "ConversationStatus",
    "DailyProjectSummary",
    "Issue",
    "IssueSeverity",
    "IssueStatus",
    "MemoryScope",
    "MemoryType",
    "MessageRole",
    "MessageStatus",
    "ProgressUpdate",
    "Project",
    "ProjectRiskLevel",
    "ProjectStatus",
    "Task",
    "TaskAiStatus",
    "TaskLink",
    "TaskLinkType",
    "TaskStatus",
    "User",
    "UserRole",
    "UserStatus",
]

# Register the shared plan-write lock once models are available.
from app.core import plan_lock as _plan_lock  # noqa: E402,F401
