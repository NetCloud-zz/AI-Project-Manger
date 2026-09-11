---
name: project-agent-overview
description: >-
  AI Project Management Agent architecture, boundaries, repo layout,
  Apache-2.0 copyright rules. Use when onboarding, refactoring structure,
  or answering "how is this repo organized".
---

# Project Agent — Overview

## Product boundary

- **Source of truth**: PostgreSQL + FastAPI services (due dates, delay, status, owners, RBAC).
- **AI**: summarization, risk hints, NLQ via Management Agent tools — never bypass permissions.
- **Industry-agnostic**: software, ops, consulting, manufacturing, product delivery, etc.
- **Optional**: LLM gateway, WeCom, OA read-only MySQL + SSO.

## Stack

- `backend/` FastAPI, SQLAlchemy 2, Alembic, Celery worker/beat
- `frontend/` Next.js + TypeScript + Ant Design
- `deploy/nginx/`, `docker-compose.yml`, `.env.example`
- Handbook: `docs/HANDBOOK.md`

## Hard rules for agents editing this repo

1. Do **not** commit `.env`, API keys, LAN IPs, DB dumps, or customer data.
2. Do **not** remove or replace copyright owner **Jack Zhang** in `LICENSE` / `NOTICE` / `COPYRIGHT`.
3. Prefer small, task-scoped diffs; match existing patterns.
4. Business writes go through services + permissions, not ad-hoc SQL in agents.
5. Keep copy industry-neutral (no single-industry jargon in defaults).
6. Respond to end users in the language they use; code comments stay consistent with the file.

## Key paths

| Area | Path |
| --- | --- |
| Config | `backend/app/core/config.py` |
| Permissions | `backend/app/core/permissions.py` |
| Agent chat | `backend/app/services/conversation.py`, `backend/app/api/v1/agent.py` |
| Tools | `backend/app/agents/` |
| Frontend agent UI | `frontend/app/agent/page.tsx` |
