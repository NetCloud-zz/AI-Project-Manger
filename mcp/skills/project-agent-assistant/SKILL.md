---
name: project-agent-assistant
description: >-
  Project Assistant chat: SSE streaming, idempotency, generation slot lock,
  stop/reclaim when user leaves the page, tool results and RBAC. Use when
  changing agent APIs, conversation UI, or LLM tool calling.
---

# Project Agent — Assistant

These instructions guide coding assistants. The application does not load this
skill at runtime; its tools and prompts are registered in backend code.

## Generation slot

- One in-flight generation per conversation (`STREAMING` message and/or `ACCEPTED|RUNNING` `AgentRequest`).
- Leaving the page: frontend should abort SSE and call stop; backend `stop_request` force-finalizes to unlock.
- Re-entry: `GET .../active-generation` restores stop UI / reclaims stale orphans.

## Streaming

- Backend SSE events: `message_start`, `heartbeat`, `delta`, `tool_start`, `tool_end`, `card`, `done`, `error`.
- Planning emits heartbeats (with optional `phase`) while waiting for the model and persists request liveness. Frontend event-name types include `heartbeat`.
- Persist terminal states: `COMPLETED` / `FAILED` / `STOPPED` / `INTERRUPTED`.
- Before marking COMPLETED, refresh DB so a concurrent stop is not overwritten.

## Models

- Read from env: `LLM_MODEL_REASONING` (chat), `LLM_MODEL_FAST` (summaries / progress).
- Empty `LLM_API_KEY` → stub; do not fake success.
- Ordinary ReAct conversations use `AGENT_RUNTIME=agentscope` (default), with AgentScope 2.x `Agent` + `Toolkit`; `legacy` uses the in-house tool loop.
- `AGENT_REASONING_ROUNDS` (default 20) and `AGENT_TOOL_CORRECTION_ROUNDS` (default 10) apply to the ordinary tool loop, not command planning.

## Command planning

- With a configured model, request ID and writes enabled, mutation or compound instructions selected by the intent heuristics enter the command planner before ordinary ReAct routing.
- Planning exposes whitelist read tools plus `plan_commands`. The model may query projects/people first; results are registered as facts and fed back into the planning context. Writes are forbidden until a validated plan executes.
- Budget is configurable: `COMMAND_PLAN_MAX_ROUNDS`, `COMMAND_PLAN_MAX_QUERY_CALLS`, `COMMAND_PLAN_MAX_REPAIR_ATTEMPTS`, `COMMAND_PLAN_MAX_SAME_ERROR` (defaults 6 / 8 / 3 / 2). Each model round is still bounded by `LLM_TIMEOUT_SECONDS`.
- Validation failures request a targeted full-plan repair; identical errors stop within the same-error budget. Intent classification routes the path; `resolve_write_authorization` alone decides writes. Weak confirmations inherit a prior mutation turn; status queries never authorize.
- Input layout does not determine task count. Do not require users to rewrite natural language, Markdown or tables into a fixed template.
- Write-step `source_text` must match authorizing text (whitespace folded). Auxiliary query quotes may be soft / unresolved and must not block the whole plan.
- A valid JSON array encoded as an `items` string is decoded once and then validated normally. Malformed items, invalid dependencies and invalid references remain errors.

## Tool calling

- Tools execute as the **current user**; reuse page/API permissions.
- Strip secrets from tool payloads; prefer lean DTOs.
- Mutations that move other tasks' dates need preview/confirm flows — do not silent-write.
- Never add `execute_sql` or let the model submit SQL.
- Prefer `query_entities`, `batch_find_users` and batch writes when their actual fields cover the request. `batch_create_tasks` supports task name, multi-owner (`owner_names` / multi-value `owner_name`), collaborators (`collaborator_names` → COLLABORATOR participants only when the user distinguishes 协作人), `work_stream`, dates and `planned_duration_days`. When people are listed without owner/collaborator distinction, write all as owners (OWNER participants + primary `owner_id`). Accept `tasks` as an alias for `items`. Milestones use `create_milestone`. Dependencies remain outside `batch_create_tasks` (plan draft / dedicated flows).
- Known tool validation failures on batch/non-atomic writes are `FAILED`; `UNKNOWN` is reserved for interrupted writes whose commit state is unclear.
- Gray switch: `COMMAND_PLAN_ENABLED` (default true). Budget: `COMMAND_PLAN_MAX_*`.
- Acceptance ops: `docs/ASSISTANT_ACCEPTANCE.md`; fixture `backend/evals/assistant_repair_24x1.yaml`.
- `draft_project_plan` is a draft workflow; applying a plan retains its validation and confirmation requirements. It is not interchangeable with immediate task creation.
- Command execution defaults to independent steps; explicitly requested all-or-nothing execution uses the supported atomic path. A batch tool can have its own transaction boundary. Do not describe an entire independent plan as one transaction.
- Batch tools use `operation_id` / `client_item_id` receipts; request-level and other tool writes have their own idempotency handling. Do not assume every write uses the batch protocol.
- Batch creation returns `verification` with resource-id field checks. Field diffs after commit are `NEEDS_REVIEW` (written, not rolled back). Do not treat write-step success alone as “all requirements completed”.

## Frontend cues

- `frontend/app/agent/page.tsx`: `sending`, stop button, `fetchActiveGeneration`, `pagehide` stop.
- Show stop when `sending` or any message `status === STREAMING`.
- Distinguish planning rejection from execution failure. Independent-step continuation applies only after a valid plan exists.
- Execution cards show step counts, write-step counts and actual created task counts separately. `needs_review` and `recovery` describe whether to restore source, retry pending steps, or manually verify interrupted items.
- Stop / leave-page reclaim finalizes stuck PLANNING or RUNNING command plans so the slot unlocks without inventing new writes.
