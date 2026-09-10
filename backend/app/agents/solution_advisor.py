"""Solution Advisor — structured AI suggestions for open issues."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway, create_llm_gateway
from app.llm.schemas import ChatMessage
from app.prompts import load_prompt

logger = get_logger(__name__)

AI_SUGGESTED_SOURCE = "AI_SUGGESTED"

SYSTEM_PROMPT = load_prompt("solution_advisor")


class AdviceOption(BaseModel):
    """One way forward, with what it costs. Options are compared, not ranked away."""

    name: str
    description: str = ""
    #: Working-day effect on the plan. Null when the evidence cannot support a number.
    time_impact_days: int | None = None
    #: People, equipment or vendor implications, in words. No capacity model exists.
    resource_impact: str | None = None
    risks: list[str] = Field(default_factory=list)


class SolutionAdvice(BaseModel):
    problem_summary: str
    possible_causes: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    suggested_participants: list[str] = Field(default_factory=list)
    escalation_recommended: bool = False
    #: Alternatives with their time and resource consequences.
    options: list[AdviceOption] = Field(default_factory=list)
    #: Which option the advice leans towards, by name. Empty when it will not choose.
    recommended_option: str | None = None
    #: Evidence ids the advice actually used, e.g. "progress#42".
    cited_sources: list[str] = Field(default_factory=list)
    #: Facts that are missing. Saying so beats inventing them.
    data_gaps: list[str] = Field(default_factory=list)


class SolutionAdvisorInput(BaseModel):
    project_goal: str | None
    project_code: str
    task_name: str | None
    task_due_date: str | None
    project_target_date: str | None = None
    issue_title: str
    issue_description: str
    issue_severity: str
    issue_status: str
    recent_progress: list[str] = Field(default_factory=list)
    historical_context: list[str] = Field(default_factory=list)
    #: Cited evidence lines from ProjectContextService, each carrying a source id.
    evidence: list[str] = Field(default_factory=list)
    #: What the evidence selection covered and deliberately left out.
    coverage_note: str | None = None
    #: Gaps found in the data before the model was asked anything.
    known_data_gaps: list[str] = Field(default_factory=list)
    #: Real names on this project, so participants are not invented.
    known_participants: list[str] = Field(default_factory=list)


class SolutionAdvisor:
    """Calls LLMGateway (reasoning model) to advise on an issue."""

    def __init__(self, gateway: LLMGateway | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._gateway = gateway or create_llm_gateway(self._settings)

    async def advise(self, data: SolutionAdvisorInput) -> SolutionAdvice:
        if not self._gateway.configured:
            msg = "LLM gateway is not configured"
            raise LLMError(msg)

        user_content = _build_user_prompt(data)
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_content),
        ]
        logger.info(
            "agent.solution_advisor.request",
            issue_title=data.issue_title,
            model=self._settings.LLM_MODEL_REASONING,
        )
        return await self._gateway.structured_output(
            messages=messages,
            schema=SolutionAdvice,
            model=self._settings.LLM_MODEL_REASONING,
        )


def serialize_ai_suggested_solution(advice: SolutionAdvice) -> str:
    """Persist structured advice with AI source marker."""
    payload = {
        "source": AI_SUGGESTED_SOURCE,
        "generated_at": datetime.now(UTC).isoformat(),
        **advice.model_dump(),
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_suggested_solution(raw: str | None) -> tuple[SolutionAdvice | None, bool]:
    """Return parsed advice and whether it is AI-suggested."""
    if not raw:
        return None, False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(data, dict) or data.get("source") != AI_SUGGESTED_SOURCE:
        return None, False
    advice_fields = {k: v for k, v in data.items() if k not in ("source", "generated_at")}
    try:
        return SolutionAdvice.model_validate(advice_fields), True
    except Exception:
        return None, True


def _build_user_prompt(data: SolutionAdvisorInput) -> str:
    recent_block = (
        "\n".join(f"- {item}" for item in data.recent_progress)
        if data.recent_progress
        else "(none)"
    )
    history_block = (
        "\n".join(f"- {item}" for item in data.historical_context)
        if data.historical_context
        else "(none)"
    )
    evidence_block = "\n".join(f"- {item}" for item in data.evidence) if data.evidence else "(none)"
    gaps_block = (
        "\n".join(f"- {item}" for item in data.known_data_gaps)
        if data.known_data_gaps
        else "(none detected)"
    )
    participants_block = (
        "、".join(data.known_participants) if data.known_participants else "(unknown)"
    )
    return (
        f"Project: {data.project_code}\n"
        f"Project goal: {data.project_goal or '(not specified)'}\n"
        f"Project target date: {data.project_target_date or '(not specified)'}\n"
        f"Task: {data.task_name or '(project-level issue; no linked task)'}\n"
        f"Task due date: {data.task_due_date or '(not applicable)'}\n"
        f"Issue title: {data.issue_title}\n"
        f"Issue severity: {data.issue_severity}\n"
        f"Issue status: {data.issue_status}\n"
        f"Issue description:\n{data.issue_description}\n"
        f"Recent progress on this task:\n{recent_block}\n"
        f"Historical context:\n{history_block}\n"
        f"Selected project evidence (cite these ids in cited_sources):\n{evidence_block}\n"
        f"Evidence coverage: {data.coverage_note or '(not provided)'}\n"
        f"Known data gaps before analysis:\n{gaps_block}\n"
        f"People on this project: {participants_block}"
    )
