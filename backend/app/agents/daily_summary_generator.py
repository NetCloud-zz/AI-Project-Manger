"""Daily project summary generator — LLM organizes DB facts only."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway, create_llm_gateway
from app.llm.schemas import ChatMessage
from app.models.project import ProjectRiskLevel
from app.prompts import load_prompt

logger = get_logger(__name__)

SYSTEM_PROMPT = load_prompt("daily_summary_generator")


class DailySummaryLLMOutput(BaseModel):
    overall_status: str
    summary: str
    today_progress: list[str] = Field(default_factory=list)
    risk_summary: str
    next_action: str
    management_attention_hint: str


class DailySummaryFacts(BaseModel):
    project_code: str
    project_name: str
    project_goal: str | None
    project_status: str
    project_risk_level: str
    target_date: str | None
    summary_date: date
    today_progress_entries: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    critical_issue_count: int = 0
    task_snapshots: list[str] = Field(default_factory=list)
    management_attention_required: bool = False
    management_attention_reasons: list[str] = Field(default_factory=list)


class DailySummaryResult(BaseModel):
    summary: str
    risk_summary: str
    next_action: str
    management_attention: str
    overall_status: str


class DailySummaryGenerator:
    """Calls LLMGateway (fast model) to produce a daily project summary."""

    def __init__(self, gateway: LLMGateway | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._gateway = gateway or create_llm_gateway(self._settings)

    async def generate(self, facts: DailySummaryFacts) -> DailySummaryResult:
        if not self._gateway.configured:
            msg = "LLM gateway is not configured"
            raise LLMError(msg)

        user_content = _build_facts_prompt(facts)
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_content),
        ]
        logger.info(
            "agent.daily_summary.request",
            project_code=facts.project_code,
            model=self._settings.LLM_MODEL_FAST,
        )
        llm_output = await self._gateway.structured_output(
            messages=messages,
            schema=DailySummaryLLMOutput,
            model=self._settings.LLM_MODEL_FAST,
        )
        return enforce_summary_facts(facts, llm_output)


def enforce_summary_facts(
    facts: DailySummaryFacts,
    llm_output: DailySummaryLLMOutput,
) -> DailySummaryResult:
    """Correct LLM output when it conflicts with authoritative DB facts."""
    expected_status = _risk_level_to_overall_status(facts.project_risk_level)
    overall_status = llm_output.overall_status.upper().strip()
    if overall_status != expected_status:
        logger.warning(
            "agent.daily_summary.status_corrected",
            project_code=facts.project_code,
            llm_status=overall_status,
            expected_status=expected_status,
        )
        overall_status = expected_status

    if _contains_conflicting_on_track(llm_output.summary, facts.project_risk_level):
        logger.warning(
            "agent.daily_summary.summary_on_track_corrected",
            project_code=facts.project_code,
        )

    summary_body = llm_output.summary
    if facts.project_risk_level == ProjectRiskLevel.DELAYED.value:
        summary_body = _replace_on_track_language(summary_body, "DELAYED")
    elif facts.project_risk_level == ProjectRiskLevel.AT_RISK.value:
        summary_body = _replace_on_track_language(summary_body, "AT_RISK")

    progress_block = ""
    if llm_output.today_progress:
        progress_block = "\n\n今日进展：\n" + "\n".join(
            f"- {item}" for item in llm_output.today_progress
        )

    summary = (f"总体状态：{overall_status}\n\n{summary_body.strip()}{progress_block}").strip()

    management_attention = "是" if facts.management_attention_required else "否"
    if facts.management_attention_required and facts.management_attention_reasons:
        management_attention = "是 — " + "；".join(facts.management_attention_reasons)

    return DailySummaryResult(
        summary=summary,
        risk_summary=llm_output.risk_summary.strip(),
        next_action=llm_output.next_action.strip(),
        management_attention=management_attention,
        overall_status=overall_status,
    )


def _risk_level_to_overall_status(risk_level: str) -> str:
    mapping = {
        ProjectRiskLevel.NORMAL.value: "ON_TRACK",
        ProjectRiskLevel.AT_RISK.value: "AT_RISK",
        ProjectRiskLevel.DELAYED.value: "DELAYED",
    }
    return mapping.get(risk_level.upper(), "ON_TRACK")


_ON_TRACK_PATTERNS = (
    re.compile(r"\bON\s*TRACK\b", re.IGNORECASE),
    re.compile(r"正常推进"),
    re.compile(r"按计划"),
)


def _contains_conflicting_on_track(text: str, risk_level: str) -> bool:
    if risk_level == ProjectRiskLevel.NORMAL.value:
        return False
    return any(pattern.search(text) for pattern in _ON_TRACK_PATTERNS)


def _replace_on_track_language(text: str, replacement: str) -> str:
    result = text
    result = re.sub(r"\bON\s*TRACK\b", replacement, result, flags=re.IGNORECASE)
    result = result.replace("正常推进", "存在风险" if replacement == "AT_RISK" else "已延期")
    result = result.replace("按计划", "需关注" if replacement == "AT_RISK" else "已滞后")
    return result


def _build_facts_prompt(facts: DailySummaryFacts) -> str:
    progress_block = (
        "\n".join(f"- {item}" for item in facts.today_progress_entries)
        if facts.today_progress_entries
        else "(no progress submitted today)"
    )
    issues_block = (
        "\n".join(f"- {item}" for item in facts.open_issues)
        if facts.open_issues
        else "(no open issues)"
    )
    tasks_block = (
        "\n".join(f"- {item}" for item in facts.task_snapshots)
        if facts.task_snapshots
        else "(no active tasks)"
    )
    mgmt_block = (
        "\n".join(f"- {item}" for item in facts.management_attention_reasons)
        if facts.management_attention_reasons
        else "(none)"
    )
    return (
        f"Summary date: {facts.summary_date.isoformat()}\n"
        f"Project: {facts.project_code} — {facts.project_name}\n"
        f"Project goal: {facts.project_goal or '(not specified)'}\n"
        f"Project status: {facts.project_status}\n"
        f"Authoritative project_risk_level: {facts.project_risk_level}\n"
        f"Required overall_status: {_risk_level_to_overall_status(facts.project_risk_level)}\n"
        f"Target date: {facts.target_date or '(not set)'}\n"
        f"Critical open issues count: {facts.critical_issue_count}\n"
        f"Management attention required (deterministic): {facts.management_attention_required}\n"
        f"Management attention reasons:\n{mgmt_block}\n"
        f"Today's progress entries:\n{progress_block}\n"
        f"Open issues:\n{issues_block}\n"
        f"Active tasks:\n{tasks_block}"
    )
