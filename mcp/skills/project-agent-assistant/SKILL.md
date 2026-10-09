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
- Validation failures request a targeted full-plan repair; identical errors stop within the same-error budget.
- Routing and write authorization come from one per-turn `TurnDecision` (`app/agents/intent.py`). `AGENT_INTENT_MODE=regex` (default) equals `resolve_write_authorization`; `hybrid` keeps regex vetoes (status / discussion never authorize) and asks `LLM_MODEL_FAST` for an `IntentVerdict` that authorizes only with confidence ≥ `AGENT_INTENT_MIN_CONFIDENCE` and verbatim evidence from the user text; failures fall back to regex. The verdict also drives `guard_mutation` in ReAct and in command execution (`planning_details.authorization`). Do not add a second authorization path.
- Input layout does not determine task count. Do not require users to rewrite natural language, Markdown or tables into a fixed template.
- Write-step `source_text` must match authorizing text (whitespace folded). Auxiliary query quotes may be soft / unresolved and must not block the whole plan.
- A valid JSON array encoded as an `items` string is decoded once and then validated normally. Malformed items, invalid dependencies and invalid references remain errors.

## Tool calling

- Tools execute as the **current user**; reuse page/API permissions.
- Strip secrets from tool payloads; prefer lean DTOs.
- Mutations that move other tasks' dates need preview/confirm flows — do not silent-write.
- Never add `execute_sql` or let the model submit SQL.
- Tool groups (`app/agents/toolsets.py`, `AGENT_TOOLSETS_ENABLED`): every tool is core or in exactly one group; group-specific prompt rules live in `prompts/toolsets/<group>.md`, not in `management_agent.md`. New niche tools go into a group; `tests/test_agent_rework.py` enforces the partition.
- Measure prompt/routing changes with `python -m app.evals` (`make eval-intent`, `make eval-agent db=...`) on a disposable database — never the live app DB.
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


## Database contract

Read [database maintenance](../project-agent-database/SKILL.md) and
`docs/database/PROJECT_DATABASE_TOOLS.md` when changing database tools. Full table
and relationship references are indexed in `mcp/database/README.md`.

- `get_database_tools`, `get_task(task_code)` and `get_plan_version` are registered
  in `backend/app/agents/database_tools.py` through the shared management executor.
  Export current schemas with `export_database_tool_definitions()`; snapshot
  `AGENT_TOOLS.md` and YAML recommendations are not runtime registrations.
- Tools permit create/read/update only. Date/duration, project goal, work-stream,
  group and branch changes require user-provided reasons under
  `backend/app/services/agent_change_policy.py`; retain audit and existing
  confirmation flows. Initial dates on a new task are not rescheduling.
- `review_project_plan_draft` and `validate_project_plan` persist review state:
  both are writes and must remain disabled for read-only regeneration.
- Preserve real task codes and all OWNER participants in task DTOs and owner
  filters. Scalar owner fields still represent the primary owner in grouping.
- When fields or behavior change, update schemas, dispatch, query allowlists,
  DTOs, prompts, relevant tests, and the corresponding database references.
