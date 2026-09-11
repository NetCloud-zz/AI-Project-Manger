"""Batch owner references: exact identities, persisted-plan recovery, no partial creates."""

from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.agent_conversation import AgentConversation
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas.agent_command import CommandPlanInput, CommandRetryInput
from app.services.agent_commands import CommandService, format_execution, resolve_refs
from app.services.agent_idempotency import begin_request
from test_command_planning_repair import actor as actor
from test_command_planning_repair import db as db


def batch_result():
    # Deliberately different from request order: references must bind by identity.
    return {
        "resolved": [
            {"input": "测试乙", "name": "测试乙", "user_id": 12},
            {"input": "测试甲", "name": "测试甲", "user_id": 11},
        ],
        "ambiguous": [],
        "not_found": [],
    }


@pytest.mark.parametrize("field", ["id", "user_id"])
def test_batch_refs_resolve_names_not_positions(field):
    result = batch_result()
    args = {"owner_ids": [{"$ref": f"owners.{name}.{field}"} for name in ["测试甲", "测试乙"]]}
    assert resolve_refs(args, {"owners": {"data": result}}) == {"owner_ids": [11, 12]}
    assert resolve_refs({"$ref": "owners.resolved.0.user_id"}, {"owners": {"data": result}}) == 12


@pytest.mark.parametrize(
    "case",
    ["missing", "partial_name", "duplicate", "ambiguous", "not_found", "wrong_shape", "missing_id"],
)
def test_batch_refs_never_guess_an_owner(case):
    result = batch_result()
    name = "测试甲"
    if case == "missing":
        name = "不存在的人"
    elif case == "partial_name":
        name = "测试"
    elif case == "duplicate":
        result["resolved"].append({"input": name, "name": name, "user_id": 99})
    elif case == "ambiguous":
        result["ambiguous"].append(
            {"input": name, "candidates": [{"user_id": 11}, {"user_id": 99}]}
        )
    elif case == "not_found":
        result["not_found"].append(name)
    elif case == "wrong_shape":
        del result["ambiguous"]
    elif case == "missing_id":
        del result["resolved"][1]["user_id"]
    with pytest.raises(KeyError):
        resolve_refs({"$ref": f"owners.{name}.id"}, {"owners": {"data": result}})


def prepare(db, actor, *, duplicate=False):
    actor.role = UserRole.ADMIN
    owners = [
        User(
            name=name,
            username=f"batch_owner_{i}",
            password_hash="unused",
            role=UserRole.PROJECT_OWNER,
        )
        for i, name in enumerate(["测试甲", "测试乙"])
    ]
    db.add_all(owners)
    if duplicate:
        db.add(
            User(
                name="测试甲",
                username="duplicate_owner",
                password_hash="unused",
                role=UserRole.PROJECT_OWNER,
            )
        )
    conversation = AgentConversation(user_id=actor.id)
    db.add(conversation)
    db.flush()
    source = "创建周末活动测试项目，负责人是测试甲和测试乙，项目时间是2026-08-13 ~ 2026-10-06"
    request, _ = begin_request(
        db,
        user_id=actor.id,
        conversation_id=conversation.id,
        client_request_id="batch-owner-regression",
        content=source,
    )
    db.commit()
    service = CommandService(db)
    plan = service.create(
        request.id,
        source,
        CommandPlanInput(
            items=[
                {
                    "item_id": "owners",
                    "tool": "batch_find_users",
                    "source_text": source,
                    "arguments": {"names": ["测试甲", "测试乙"]},
                },
                {
                    "item_id": "project",
                    "tool": "create_project",
                    "source_text": source,
                    "depends_on": ["owners"],
                    "arguments": {
                        "project_code": "PRJ-1001",
                        "project_name": "周末活动测试项目",
                        "start_date": "2026-08-13",
                        "target_date": "2026-10-06",
                        "owner_ids": [{"$ref": "owners.测试甲.id"}, {"$ref": "owners.测试乙.id"}],
                    },
                },
            ]
        ),
    )
    return service, plan, owners


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_batch_owner_create_and_resume_preserve_both_owners(db, actor, resume):
    service, plan, owners = prepare(db, actor)
    if resume:
        # Reproduce the old executor failure, leaving the successful read receipt intact.
        original = resolve_refs

        def old_resolver(value, results):
            if isinstance(value, dict) and "owner_ids" in value:
                raise KeyError("测试甲")
            return original(value, results)

        with patch("app.services.agent_commands.resolve_refs", side_effect=old_resolver):
            failed = await service.run(plan, actor)
        assert failed["status"] == "PARTIAL"
        assert failed["business_succeeded"] == 0
        assert db.scalar(select(func.count()).select_from(Project)) == 0
        summary = format_execution(failed)
        assert "业务写入成功 0 项" in summary
        assert "批量查询负责人" in summary
        service.retry(
            plan, CommandRetryInput(expected_revision=failed["revision"], item_ids=["project"])
        )

    result = await service.run(plan, actor)
    assert result["status"] == "COMPLETED"
    assert result["business_succeeded"] == 1
    assert result["items"][0]["attempts"] == 1  # A saved successful read was not executed again.
    project = db.scalar(select(Project))
    assert db.scalar(select(func.count()).select_from(Project)) == 1
    assert {user.id for user in project.owners} == {user.id for user in owners}
    assert project.owner_id == owners[0].id
    assert project.start_date == date(2026, 8, 13)
    assert project.target_date == date(2026, 10, 6)


@pytest.mark.asyncio
async def test_ambiguous_owner_blocks_whole_project_creation(db, actor):
    service, plan, _ = prepare(db, actor, duplicate=True)
    result = await service.run(plan, actor)
    assert result["items"][0]["state"] == "SUCCEEDED"
    assert result["items"][1]["state"] == "FAILED"
    assert result["business_succeeded"] == 0
    assert db.scalar(select(func.count()).select_from(Project)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["permission", "invalid_second_owner"])
async def test_explicit_owners_keep_permission_and_transaction_checks(db, actor, case):
    service, plan, _ = prepare(db, actor)
    if case == "permission":
        actor.role = UserRole.PROJECT_OWNER
    else:
        item = service.items(plan)[1]
        item.arguments = {**item.arguments, "owner_ids": [*item.arguments["owner_ids"], 999999]}
    db.commit()
    result = await service.run(plan, actor)
    assert result["items"][1]["state"] == "FAILED"
    assert result["business_succeeded"] == 0
    assert db.scalar(select(func.count()).select_from(Project)) == 0
