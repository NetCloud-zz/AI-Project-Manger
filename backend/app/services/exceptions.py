"""Domain-specific exceptions for project and task services."""

from __future__ import annotations


class DomainValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ProjectNotFoundError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class ProjectCodeExistsError(Exception):
    pass


class OwnerNotFoundError(Exception):
    pass


class IssueNotFoundError(Exception):
    pass


class ActionItemNotFoundError(Exception):
    pass


class TaskLinkNotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    """Raised when the actor lacks permission for a resource."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        self.message = message
        super().__init__(message)


class VersionConflictError(Exception):
    """Optimistic lock failure — caller must re-read and retry."""

    def __init__(self, message: str = "VERSION_CONFLICT", *, current: dict | None = None) -> None:
        self.message = message
        self.current = current or {}
        super().__init__(message)


class ConversationNotFoundError(Exception):
    pass


class AgentMessageNotFoundError(Exception):
    pass


class MemoryNotFoundError(Exception):
    pass
