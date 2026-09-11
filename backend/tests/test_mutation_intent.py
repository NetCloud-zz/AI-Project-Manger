"""Mutation-intent / command-plan heuristics (CMD-01 + exploratory NL-01/05)."""

from __future__ import annotations

from app.schemas.agent_command import requires_atomic
from app.services.agent_entities import (
    EntityResolutionError,
    authorization_source,
    guard_mutation,
    has_mutation_intent,
    is_status_query,
    should_use_command_plan,
)


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


def test_natural_create_and_confirm_authorize_writes():
    assert has_mutation_intent("那就弄个小项目吧，叫周五咖啡角测试") is True
    assert has_mutation_intent("帮我建个旧书交换测试项目，我负责") is True
    assert has_mutation_intent("好啊，弄起来吧") is True
    assert has_mutation_intent("行，就按你说的建好") is True
    assert has_mutation_intent("确认创建 PRJ-9001") is True
    for phrase in (
        "那就弄个小项目吧，叫周五咖啡角测试",
        "帮我建个旧书交换测试项目",
        "好啊，弄起来吧",
        "行，就按你说的建好",
    ):
        guard_mutation(phrase, "create_project", {"project_name": "x"})


def test_status_query_does_not_authorize_writes():
    phrase = "散步这个到底有没有建好？"
    assert is_status_query(phrase) is True
    assert has_mutation_intent(phrase) is False
    try:
        guard_mutation(phrase, "create_project", {"project_name": "秋日散步测试项目"})
        raise AssertionError("expected CONFIRMATION_REQUIRED")
    except EntityResolutionError as exc:
        assert exc.code == "CONFIRMATION_REQUIRED"


def test_cancel_create_does_not_authorize():
    assert has_mutation_intent("先算了，别建了") is False


def test_confirmation_inherits_prior_create_intent():
    prior = "帮我建个旧书交换测试项目，我负责，十月十号弄完"
    confirm = "行，就按你说的建好，弄完告诉我在哪里看"
    assert authorization_source(confirm, [prior]) == confirm
    assert has_mutation_intent(confirm) is True
    # Weak confirm inherits prior create authorization.
    weak = "可以了"
    assert has_mutation_intent(weak) is False
    assert authorization_source(weak, [prior]) == prior
    assert has_mutation_intent(authorization_source(weak, [prior])) is True
    # Status query never inherits.
    assert authorization_source("到底有没有建好？", [prior]) == "到底有没有建好？"
    assert has_mutation_intent(authorization_source("到底有没有建好？", [prior])) is False
