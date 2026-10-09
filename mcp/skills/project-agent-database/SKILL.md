---
name: project-agent-database
description: >-
  Maintain this project's database-backed features: table and relationship changes,
  SQLAlchemy models, Alembic migrations, permissions, query fields, and assistant
  database tools. Use docs/database metadata to trace change impact and keep the
  documentation aligned with implementation.
---

# Project Agent — Database

Copyright 2024–2026 Jack Zhang. Apache License 2.0; retain NOTICE attribution.

This skill guides coding assistants inside this repository. It does not install
an MCP server or grant database access. Paths in code spans are relative to the
repository root; when this skill is copied elsewhere, locate the checkout first.

## Read according to the change

Start with [database navigation](../../database/README.md)
(`mcp/database/README.md`) and `docs/database/PROJECT_DATABASE_TOOLS.md`.
Use the navigation's links to read only the relevant detail:

- Columns, constraints, defaults or indexes: `DATABASE_DICTIONARY.md` and the
  target table in `database_schema.json`; compare models and Alembic migrations.
- Relationships or dependency effects: `DATABASE_RELATIONSHIPS.md` and
  `DATABASE_ER.md`; inferred relationships are not confirmed joins.
- Query/assistant behavior: `AGENT_QUERY_RULES.md`, `AGENT_DATABASE_GUIDE.md`,
  relevant entities in `agent_semantic_layer.yaml`, and actual tool schemas.
- Migration or integrity work: `DATABASE_RISKS.md`, checking each finding against
  current code and, when the task calls for it, read-only database metadata.

All detail filenames above live in `docs/database/`. The machine-readable file
index is `mcp/database/resources.json`; its paths are repository-root relative.
The detail files remain in one maintained location and must accompany the checkout.

## Facts that affect implementation

- The structure snapshot was collected on 2026-09-15; it is not proof of the
  current deployment. Distinguish observed database structure, ORM/migration
  intent, and suggested tool capabilities. Do not mark an old risk fixed merely
  because a newer tool description exists.
- `task_code` now maps to the business code, not `id`. Owner filters include
  primary + OWNER participants, while scalar owner grouping is primary-only.
- `work_stream` is text; TaskGroup is a tree. ProjectOwner, ProjectMember,
  TaskParticipant and alternative-route entities are not interchangeable.
- Preserve `can_view_task` and full-project access checks in addition to project
  visibility. There is no general tenant key or universal soft-delete contract.
- Runtime assistant tools permit create/read/update only, through business
  services. No delete, raw SQL, DDL, or model-supplied credentials/actor identity.
- `agent_change_policy.py` enforces reasons for date/duration, project `goal`,
  work-stream/group and branch changes. Reasons come from the user and are
  audited; they do not replace authorization or schedule preview/confirmation.
- Draft review/validation persists state and belongs to WRITE_TOOLS. Keep this
  classification consistent across AgentScope, legacy, planning and regeneration.

## Complete a database-related change

Trace the affected model, request/response schema, service, permissions, tool
schema and DTO before editing. Update the relevant query whitelist and prompt
when exposing fields to the assistant, and verify scope and mutation behavior.

When the requested development work requires DDL, use the repository's Alembic
workflow and deployment skill. Creating/updating documentation does not require
applying migrations. Keep business data and secrets out of reference files.

Update the affected canonical details under `docs/database/`; retain collection
provenance and explicitly label unverified schema expectations. Refresh the
resource index only when its paths or roles change. Keep version changelogs under
`docs/releases/`. Verify links, changed schemas and task-relevant tests before
reporting what was changed, tested, and actually deployed.
