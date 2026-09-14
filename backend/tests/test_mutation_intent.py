"""Mutation-intent / command-plan heuristics (CMD-01 + exploratory NL-01/05)."""

from __future__ import annotations

from app.schemas.agent_command import requires_atomic
from app.services.agent_entities import (
    EntityResolutionError,
    authorization_source,
    classify_assistant_intent,
    guard_mutation,
    has_mutation_intent,
    is_status_query,
    resolve_write_authorization,
    should_use_command_plan,
    writes_authorized,
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
    from app.services.agent_entities import plan_coverage_source

    assert plan_coverage_source(confirm, [prior]) == prior
    # Weak confirm inherits prior create authorization.
    weak = "可以了"
    assert has_mutation_intent(weak) is False
    assert writes_authorized(weak, [prior]) is True
    assert authorization_source(weak, [prior]) == prior
    assert plan_coverage_source(weak, [prior]) == prior
    assert has_mutation_intent(authorization_source(weak, [prior])) is True
    # Weak confirm alone never authorizes.
    assert writes_authorized(weak) is False
    assert resolve_write_authorization(weak) is None
    # Status query never inherits.
    assert authorization_source("到底有没有建好？", [prior]) == "到底有没有建好？"
    assert has_mutation_intent(authorization_source("到底有没有建好？", [prior])) is False
    assert writes_authorized("到底有没有建好？", [prior]) is False
    assert classify_assistant_intent("到底有没有建好？") == "status"
    assert classify_assistant_intent(weak) == "weak_confirmation"
    assert classify_assistant_intent(prior) == "mutation"


def test_confirm_create_n_uses_prior_detail_for_coverage():
    from app.services.agent_entities import plan_coverage_source

    prior = (
        "NLRP3项目： # 创建任务 ## 一、药物化学（阶段）\n"
        "1. **中间体合成（三环）** * 负责人：孙建波 * 时间：2026-08-28 ~ 2026-09-28"
    )
    confirm = (
        "确认创建这 24 条任务，里程碑 Preclinical profile 的 2026-10-06 不需要补到该里程碑上，"
        "4 个「待定」负责人与 5 个待定日期后续补齐，本次先留空"
    )
    assert writes_authorized(confirm, [prior, "重新在处理一次"]) is True
    assert plan_coverage_source(confirm, [prior, "重新在处理一次"]) == prior
