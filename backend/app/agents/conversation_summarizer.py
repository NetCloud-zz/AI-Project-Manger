"""Rolling conversation summary — Fast model, facts stay out of the summary."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.llm.base import LLMError
from app.llm.gateway import LLMGateway, create_llm_gateway
from app.llm.schemas import ChatMessage
from app.models.agent_conversation import AgentMessage, MessageRole
from app.prompts import load_prompt

logger = get_logger(__name__)

SYSTEM_PROMPT = load_prompt("conversation_summary")


class ConversationSummaryOutput(BaseModel):
    summary: str = Field(min_length=1)


class ConversationSummarizer:
    def __init__(
        self,
        gateway: LLMGateway | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._gateway = gateway or create_llm_gateway(self._settings)

    async def summarize(self, messages: list[AgentMessage]) -> str:
        if not self._gateway.configured:
            msg = "LLM gateway is not configured"
            raise LLMError(msg)

        transcript = _format_transcript(messages)
        result = await self._gateway.structured_output(
            messages=[
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(
                    role="user",
                    content=(
                        "Summarize this assistant conversation transcript:\n\n"
                        f"{transcript}"
                    ),
                ),
            ],
            schema=ConversationSummaryOutput,
            model=self._settings.LLM_MODEL_FAST,
        )
        logger.info(
            "agent.conversation_summary.generated",
            message_count=len(messages),
            summary_chars=len(result.summary),
        )
        return result.summary.strip()


def _format_transcript(messages: list[AgentMessage], *, max_chars: int = 12000) -> str:
    lines: list[str] = []
    for msg in messages:
        if msg.role not in (MessageRole.USER, MessageRole.ASSISTANT):
            continue
        label = "User" if msg.role == MessageRole.USER else "Assistant"
        content = (msg.content or "").strip()
        if not content:
            continue
        lines.append(f"{label}: {content}")
    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
