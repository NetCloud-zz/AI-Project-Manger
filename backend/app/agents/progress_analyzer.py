"""Progress update analyzer — converts natural language to structured fields."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway, create_llm_gateway
from app.llm.schemas import ChatMessage
from app.models.task import TaskAiStatus
from app.prompts import load_prompt

logger = get_logger(__name__)

SYSTEM_PROMPT = load_prompt("progress_analyzer")


class IssueSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProgressIssue(BaseModel):
    title: str
    description: str
    severity: IssueSeverity


class ProgressAnalysisResult(BaseModel):
    summary: str
    status: TaskAiStatus
    risk: bool
    risk_reason: str | None = None
    issue_detected: bool
    issue: ProgressIssue | None = None


class ProgressAnalyzerInput(BaseModel):
    project_goal: str | None
    task_name: str
    due_date: date | None = None
    current_date: date
    historical_progress: list[str] = Field(default_factory=list)
    today_update: str


class ProgressAnalyzer:
    """Calls LLMGateway to analyse a single progress submission."""

    def __init__(self, gateway: LLMGateway | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._gateway = gateway or create_llm_gateway(self._settings)

    async def analyze(self, data: ProgressAnalyzerInput) -> ProgressAnalysisResult:
        if not self._gateway.configured:
            msg = "LLM gateway is not configured"
            raise LLMError(msg)

        user_content = _build_user_prompt(data)
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="user", content=user_content),
        ]
        logger.info(
            "agent.progress_analyzer.request",
            task_name=data.task_name,
            model=self._settings.LLM_MODEL_FAST,
        )
        return await self._gateway.structured_output(
            messages=messages,
            schema=ProgressAnalysisResult,
            model=self._settings.LLM_MODEL_FAST,
        )


def _build_user_prompt(data: ProgressAnalyzerInput) -> str:
    history_block = (
        "\n".join(f"- {item}" for item in data.historical_progress)
        if data.historical_progress
        else "(none)"
    )
    return (
        f"Project goal: {data.project_goal or '(not specified)'}\n"
        f"Task: {data.task_name}\n"
        f"Due date: {data.due_date.isoformat() if data.due_date else '(not set)'}\n"
        f"Current date: {data.current_date.isoformat()}\n"
        f"Historical progress:\n{history_block}\n"
        f"Today's update:\n{data.today_update}"
    )
