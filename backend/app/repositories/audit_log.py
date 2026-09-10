"""Audit log data access."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, entry: AuditLog) -> AuditLog:
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_by_id(self, audit_id: int) -> AuditLog | None:
        return self.db.get(AuditLog, audit_id)
