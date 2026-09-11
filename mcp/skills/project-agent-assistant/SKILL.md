---
name: project-agent-assistant
description: >-
  Project Assistant chat: SSE streaming, idempotency, generation slot lock,
  stop/reclaim when user leaves the page, tool results and RBAC. Use when
  changing agent APIs, conversation UI, or LLM tool calling.
---

# Project Agent — Assistant

## Generation slot

- One in-flight generation per conversation (`STREAMING` message and/or `ACCEPTED|RUNNING` `AgentRequest`).
- Leaving the page: frontend should abort SSE and call stop; backend `stop_request` force-finalizes to unlock.
- Re-entry: `GET .../active-generation` restores stop UI / reclaims stale orphans.

## Streaming

- SSE events: `message_start`, `delta`, `tool_*`, `done`, `error`.
- Persist terminal states: `COMPLETED` / `FAILED` / `STOPPED` / `INTERRUPTED`.
- Before marking COMPLETED, refresh DB so a concurrent stop is not overwritten.

## Models

- Read from env: `LLM_MODEL_REASONING` (chat), `LLM_MODEL_FAST` (summaries / progress).
- Empty `LLM_API_KEY` → stub; do not fake success.
- Assistant ReAct runtime: `AGENT_RUNTIME=agentscope` (default) uses AgentScope 2.x `Agent` + `Toolkit`; `legacy` keeps the in-house tool loop. Command planning, stub fallback, SSE and RBAC tools are unchanged.
- Reasoning vs correction: `AGENT_REASONING_ROUNDS` (default 20) and `AGENT_TOOL_CORRECTION_ROUNDS` (default 10). Prefer `query_entities`, `batch_find_users`, `draft_project_plan` / `batch_create_tasks` over per-row tools. Agent never emits SQL.

## Tool calling

- Tools execute as the **current user**; reuse page/API permissions.
- Strip secrets from tool payloads; prefer lean DTOs.
- Mutations that move other tasks' dates need preview/confirm flows — do not silent-write.
- Never add `execute_sql` or let the model submit SQL. Prefer `query_entities` and batch tools; writes use one transaction plus `operation_id` / `client_item_id` idempotency and a post-write `verification` payload.

## Frontend cues

- `frontend/app/agent/page.tsx`: `sending`, stop button, `fetchActiveGeneration`, `pagehide` stop.
- Show stop when `sending` or any message `status === STREAMING`.
