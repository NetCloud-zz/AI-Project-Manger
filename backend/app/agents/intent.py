"""Per-turn intent and write authorization (single decision point).

``regex`` mode reproduces the heuristic rules in ``services.agent_entities``
exactly. ``hybrid`` mode keeps the regex vetoes (status follow-ups and explicit
read-only / discussion framing never authorize) and otherwise asks the fast
model for a structured verdict. A model verdict authorizes writes only with
enough confidence and a verbatim evidence span from the user's own text; any
model failure falls back to the regex decision.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.logging import get_logger
from app.llm.schemas import ChatMessage
from app.prompts import load_prompt
from app.services.agent_entities import (
    authorization_source,
    classify_assistant_intent,
    is_compound_instruction,
    is_status_query,
    plan_coverage_source,
    resolve_write_authorization,
    should_use_command_plan,
)

logger = get_logger(__name__)

_PRIOR_WINDOW = 4
_MIN_EVIDENCE_CHARS = 2


class IntentVerdict(BaseModel):
    intent: Literal["write", "confirm_previous", "status_check", "discussion", "query", "other"]
    writes_requested: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str = ""
    confirmed_prior: int | None = None


@dataclass(frozen=True, slots=True)
class TurnDecision:
    mode: str
    decided_by: str
    intent: str
    authorization_source: str | None
    coverage_source: str
    route_command_plan: bool
    verdict: dict[str, Any] | None = None
    fallback_reason: str | None = None

    @property
    def writes_authorized(self) -> bool:
        return self.authorization_source is not None

    @property
    def guard_authorized(self) -> bool | None:
        """Explicit verdict for ``guard_mutation``; ``None`` keeps the regex guard."""
        if self.mode == "regex":
            return None
        return self.writes_authorized

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("authorization_source", None)
        payload.pop("coverage_source", None)
        payload["writes_authorized"] = self.writes_authorized
        return payload


def regex_decision(message: str, prior: list[str], *, mode: str = "regex") -> TurnDecision:
    auth = resolve_write_authorization(message, prior)
    return TurnDecision(
        mode=mode,
        decided_by="regex",
        intent=classify_assistant_intent(message),
        authorization_source=auth,
        coverage_source=plan_coverage_source(message, prior),
        route_command_plan=should_use_command_plan(authorization_source(message, prior)),
    )


def _fold(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def evidence_in_message(evidence: str, message: str) -> bool:
    folded, whole = _fold(evidence), _fold(message)
    if not folded:
        return False
    return folded == whole or (len(folded) >= _MIN_EVIDENCE_CHARS and folded in whole)


def _classifier_messages(message: str, prior: list[str]) -> list[ChatMessage]:
    recent = prior[-_PRIOR_WINDOW:]
    lines = ["历史用户消息（编号从 0 开始，越大越近）："]
    if recent:
        lines += [f"[{index}] {text}" for index, text in enumerate(recent)]
    else:
        lines.append("（无）")
    lines += ["", "当前消息：", message]
    return [
        ChatMessage(role="system", content=load_prompt("intent_classifier")),
        ChatMessage(role="user", content="\n".join(lines)),
    ]


def _apply_verdict(
    verdict: IntentVerdict,
    *,
    message: str,
    prior: list[str],
    settings: Settings,
    base: TurnDecision,
) -> TurnDecision:
    recent = prior[-_PRIOR_WINDOW:]
    trusted = verdict.confidence >= settings.AGENT_INTENT_MIN_CONFIDENCE and evidence_in_message(
        verdict.evidence, message
    )
    auth: str | None = None
    intent = "general"
    coverage = message
    if verdict.intent == "write" and verdict.writes_requested and trusted:
        auth, intent = message, "mutation"
    elif verdict.intent == "confirm_previous" and verdict.writes_requested and trusted:
        index = verdict.confirmed_prior
        if index is not None and 0 <= index < len(recent) and not is_status_query(recent[index]):
            auth = recent[index]
            intent = "confirmation"
            coverage = base.coverage_source if base.writes_authorized else auth
    elif verdict.intent == "status_check":
        intent = "status"
    elif verdict.intent == "discussion":
        intent = "discussion"
    route = auth is not None or (
        intent not in {"status", "discussion"} and is_compound_instruction(message)
    )
    return TurnDecision(
        mode="hybrid",
        decided_by="llm",
        intent=intent,
        authorization_source=auth,
        coverage_source=coverage,
        route_command_plan=route,
        verdict=verdict.model_dump(),
    )


async def decide_turn(
    message: str,
    prior: list[str],
    *,
    settings: Settings,
    gateway: Any | None,
) -> TurnDecision:
    """Return the routing + write-authorization decision for this user turn."""
    if settings.AGENT_INTENT_MODE != "hybrid":
        return regex_decision(message, prior)

    base = regex_decision(message, prior, mode="hybrid")
    if base.intent in {"status", "discussion"}:
        return replace(base, decided_by="regex_veto")

    structured = getattr(gateway, "structured_output", None)
    if gateway is None or not getattr(gateway, "configured", False) or structured is None:
        return replace(base, decided_by="regex_fallback", fallback_reason="gateway_unavailable")
    try:
        verdict = await asyncio.wait_for(
            structured(
                messages=_classifier_messages(message, prior),
                schema=IntentVerdict,
                model=settings.LLM_MODEL_FAST,
            ),
            timeout=settings.AGENT_INTENT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — any classifier failure keeps regex behaviour
        logger.warning("agent.intent.fallback", error=type(exc).__name__)
        return replace(base, decided_by="regex_fallback", fallback_reason=type(exc).__name__)
    return _apply_verdict(verdict, message=message, prior=prior, settings=settings, base=base)
