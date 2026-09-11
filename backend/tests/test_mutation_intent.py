"""Mutation-intent / command-plan heuristics (CMD-01 guard regression)."""

from __future__ import annotations

from app.schemas.agent_command import requires_atomic
from app.services.agent_entities import has_mutation_intent, should_use_command_plan


def test_create_n_with_do_not_create_others_still_authorizes_writes():
    source = (
        "请在项目 QA-P3-1 中创建恰好 3 个新任务，名称必须完全一致：A；B；C。"
        "不要创建其它任务。"
    )
    assert has_mutation_intent(source) is True
    assert should_use_command_plan(source) is True
    assert requires_atomic(source) is False


def test_discussion_only_blocks_writes():
    source = "只是讨论如何拆分里程碑，明确不要创建、不要修改、不要删除任何任务或项目。"
    assert has_mutation_intent(source) is False
    assert should_use_command_plan(source) is False
