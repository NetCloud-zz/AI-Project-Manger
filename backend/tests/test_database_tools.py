"""Project database contract regression tests. Copyright 2024–2026 Jack Zhang."""

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.agents.database_tools import database_tool_catalog
from app.agents.management_tools import MANAGEMENT_TOOLS, WRITE_TOOLS, ManagementToolExecutor
from app.agents.query.fields import TASK_QUERY_FIELDS
from app.agents.registry import ToolRiskLevel, get_tool_registry
from app.core.database import Base
from app.models.audit_log import AuditLog
from app.models.planning import PlanVersion, TaskParticipant
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.services.agent_batch import AgentBatchService
from app.services.agent_change_policy import REASON_FIELDS, require_change_reason
from app.services.exceptions import DomainValidationError, PermissionDeniedError
from app.services.management_query import ManagementQueryService
from app.services.management_write import ManagementWriteService


@pytest.fixture
def context():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        admin = User(name="甲", username="admin", password_hash="unused", role=UserRole.ADMIN)
        member = User(name="乙", username="member", password_hash="unused", role=UserRole.MEMBER)
        db.add_all([admin, member])
        db.flush()
        project = Project(project_code="PRJ-1001", project_name="演示", owner_id=admin.id)
        db.add(project)
        db.flush()
        task = Task(
            project_id=project.id,
            task_code="T20260915-001",
            task_name="评审",
            owner_id=admin.id,
            status=TaskStatus.COMPLETED,
            is_active_branch=True,
        )
        db.add(task)
        db.commit()
        yield db, admin, member, project, task
    engine.dispose()


@pytest.mark.parametrize("tool,field", [(t, f) for t, fs in REASON_FIELDS.items() for f in fs])
@pytest.mark.parametrize("reason", [None, "", "  ", 123, "a"])
def test_sensitive_fields_cannot_be_cleared_without_reason(tool, field, reason):
    with pytest.raises(DomainValidationError):
        require_change_reason(tool, {field: None, "change_reason": reason})


def test_create_initial_dates_need_no_reason():
    assert require_change_reason("create_task", {"due_date": "2026-10-01"}) is None
    assert require_change_reason("update_task", {"progress_percent": 50}) is None


def test_read_only_review_and_catalog(context):
    db, admin, *_ = context
    executor = ManagementToolExecutor(db, admin, allow_writes=False)
    for name in ("review_project_plan_draft", "validate_project_plan"):
        assert name in WRITE_TOOLS
        assert get_tool_registry().require(name).risk_level != ToolRiskLevel.READ
        result = executor.execute_result(name, {"draft_id": "missing"})
        assert not result.ok
        assert result.error.code.value == "WRITE_DISABLED"
    catalog = executor.execute_result("get_database_tools").data
    assert catalog["delete_allowed"] is False
    assert not executor.execute_result("delete_task", {"task_id": 1}).ok
    assert {t.name for t in MANAGEMENT_TOOLS} == {
        t["name"] for t in database_tool_catalog()["tools"]
    }


def test_direction_reason_persists_and_missing_reason_does_not_write(context):
    db, admin, _, project, _ = context
    service = ManagementWriteService(db)
    with pytest.raises(DomainValidationError):
        service.update_project(admin, {"project_id": project.id, "goal": "新方向"})
    assert project.goal is None
    result = service.update_project(
        admin, {"project_id": project.id, "goal": "新方向", "change_reason": "  交付范围调整  "}
    )
    assert result["ok"]
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "agent.change_reason"))
    assert audit.new_value["change_reason"] == "交付范围调整"
    assert audit.resource_id == str(project.id)


def test_task_code_and_equal_owners(context):
    db, admin, member, project, task = context
    db.add(TaskParticipant(task_id=task.id, user_id=member.id, role="OWNER"))
    db.commit()
    query = ManagementQueryService(db)
    result = ManagementToolExecutor(db, admin).execute_result(
        "get_task", {"task_code": task.task_code}
    )
    assert result.ok
    assert result.data["task"]["task_code"] == task.task_code
    assert result.data["task"]["owner_ids"] == [admin.id, member.id]
    assert TASK_QUERY_FIELDS["task_code"] == "task_code"
    for field, value in [
        ("task_code", task.task_code),
        ("owner_id", member.id),
        ("owner_name", member.name),
    ]:
        result = query.query_entities(
            admin, {"entity": "task", "filters": [{"field": field, "op": "eq", "value": value}]}
        )
        assert result["total"] == 1
    assert (
        query.search_tasks(admin, owner_scope="user", owner_id=member.id, include_inactive=True)[
            "total"
        ]
        == 1
    )
    db.delete(db.get(TaskParticipant, (task.id, member.id)))
    db.commit()
    assert query.get_task(member, task_code=task.task_code)["found"] is False


def test_plan_version_is_summary_and_requires_full_scope(context):
    db, admin, member, project, task = context
    db.add_all(
        [
            PlanVersion(
                project_id=project.id,
                version=1,
                reason="初始计划",
                snapshot={"private": "never return"},
            ),
            TaskParticipant(task_id=task.id, user_id=member.id, role="OWNER"),
        ]
    )
    db.commit()
    query = ManagementQueryService(db)
    args = {"project_id": project.id, "version": 1}
    result = query.get_plan_version(admin, args)
    assert result["found"] and "snapshot" not in result
    with pytest.raises(PermissionDeniedError):
        query.get_plan_version(member, args)


def test_batch_sensitive_change_requires_reason_and_rejects_silent_fields(context):
    db, admin, _, _, task = context
    service = AgentBatchService(db)
    for fields in [
        {"work_stream": "新工作流"},
        {"due_date": "2026-10-01", "change_reason": "调整交付"},
    ]:
        with pytest.raises(DomainValidationError):
            service.batch_update_tasks(admin, {"items": [{"task_id": task.id, **fields}]})
    assert task.work_stream is None
    result = service.batch_update_tasks(
        admin,
        {"items": [{"task_id": task.id, "work_stream": "交付", "change_reason": "调整执行路线"}]},
    )
    assert result["ok"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "agent.change_reason")) is not None


def test_completed_tasks_counted_in_progress_overview(context):
    db, admin, _, project, _ = context
    result = ManagementQueryService(db).get_project_progress_overview(admin, project_id=project.id)
    assert result["counts"]["completed"] == 1


def test_reschedule_reason_is_forwarded(context):
    db, admin, _, _, task = context
    service = ManagementWriteService(db)
    with pytest.raises(DomainValidationError):
        service.reschedule_task(admin, {"task_id": task.id, "due_date": "2026-10-01"})
    task.status = TaskStatus.TODO
    db.commit()
    result = service.reschedule_task(
        admin, {"task_id": task.id, "due_date": "2026-10-01", "change_reason": "评审时间调整"}
    )
    assert result["ok"]
    assert task.due_date == date(2026, 10, 1)


def test_assign_task_still_works_without_change_reason(context):
    db, admin, member, _, task = context
    result = ManagementWriteService(db).assign_task(admin, {
        "task_id": task.id, "owner_id": member.id,
    })
    assert result["ok"] and task.owner_id == member.id
