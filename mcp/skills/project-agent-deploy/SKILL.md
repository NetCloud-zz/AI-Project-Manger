---
name: project-agent-deploy
description: >-
  Deploy and operate Project Agent with Docker Compose or local venv.
  Use for env setup, migrations, health checks, and release rebuilds.
---

# Project Agent — Deploy

## Safe config

```bash
cp .env.example .env
# Set JWT_SECRET, POSTGRES_PASSWORD, optional LLM_* / WECOM_* / OA_*
# Never commit .env
```

## Compose

```bash
docker compose up -d --build
docker compose ps
curl -sS http://localhost/health
curl -sS http://localhost/health/ready
```

After code changes to backend/frontend images (sources not bind-mounted):

```bash
docker compose build backend frontend
docker compose up -d --force-recreate backend frontend
```

## Migrations

```bash
cd backend && alembic upgrade head
# Ensure a single head before upgrading
```

Backup Postgres before upgrade. Downgrade is not a business rollback.

## Ops checklist

| Symptom | Likely cause |
| --- | --- |
| UI ok, no notifications | Worker down |
| AI always stub | `LLM_*` empty or wrong |
| CORS / blank API on :3000 | Use Nginx entry, or set `NEXT_PUBLIC_API_BASE_URL` |
| "生成进行中" stuck | Call stop / `active-generation` reclaim |

## Seed

`make seed` creates demo users from `SEED_*_PASSWORD`. Do not use defaults on shared hosts.
