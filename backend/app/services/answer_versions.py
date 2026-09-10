"""Helpers for OPT-04 answer version association."""

from __future__ import annotations

from app.models.agent_conversation import AgentMessage, MessageRole


def resolve_parent_user_message(
    messages: list[AgentMessage],
    target: AgentMessage,
) -> AgentMessage | None:
    """Return the USER turn this assistant answer belongs to.

    Prefer explicit parent_user_message_id (including when regenerating a
    regenerated answer). Fall back to the nearest preceding USER only for
    legacy messages without a stored association.
    """
    if target.role != MessageRole.ASSISTANT:
        return None

    by_id = {m.id: m for m in messages}
    if target.parent_user_message_id is not None:
        parent = by_id.get(target.parent_user_message_id)
        if parent is not None and parent.role == MessageRole.USER:
            return parent

    for msg in reversed(messages):
        if msg.id >= target.id:
            continue
        if msg.role == MessageRole.USER:
            return msg
    return None


def next_answer_version(messages: list[AgentMessage], parent_user_id: int) -> int:
    versions = [
        m.answer_version or 0
        for m in messages
        if m.role == MessageRole.ASSISTANT and m.parent_user_message_id == parent_user_id
    ]
    return (max(versions) if versions else 0) + 1


def selected_context_messages(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Keep USER turns and only the selected (or latest) ASSISTANT version each."""
    selected: dict[int, int] = {}
    latest: dict[int, AgentMessage] = {}
    for msg in messages:
        if msg.role != MessageRole.ASSISTANT or msg.parent_user_message_id is None:
            continue
        parent_id = msg.parent_user_message_id
        prev = latest.get(parent_id)
        if prev is None or (msg.answer_version or 0) >= (prev.answer_version or 0):
            latest[parent_id] = msg
    for msg in messages:
        if msg.role == MessageRole.USER and msg.selected_answer_id is not None:
            selected[msg.id] = msg.selected_answer_id

    kept: list[AgentMessage] = []
    for msg in messages:
        if msg.role != MessageRole.ASSISTANT:
            kept.append(msg)
            continue
        parent_id = msg.parent_user_message_id
        if parent_id is None:
            # Legacy unbound assistant — keep for continuity, do not invent links.
            kept.append(msg)
            continue
        chosen_id = selected.get(parent_id)
        if chosen_id is None:
            chosen = latest.get(parent_id)
            chosen_id = chosen.id if chosen is not None else None
        if chosen_id is None or msg.id == chosen_id:
            kept.append(msg)
    return kept
