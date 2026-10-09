---
name: project-agent-deploy
description: >-
  Deploy and operate Project Agent with Docker Compose or local venv.
  Use for env setup, migrations, health checks, and release rebuilds.
---

# Project Agent — Deploy

## Safe config

```bash
test -f .env || cp .env.example .env
# Set JWT_SECRET, POSTGRES_PASSWORD, optional LLM_* / WECOM_* / OA_*
# Never commit .env
```

The repository Compose configuration passes an explicit environment map to
containers. A variable in the host `.env` is not automatically a container
variable. `AGENT_RUNTIME`, reasoning/correction rounds, and `COMMAND_PLAN_*`
are included in that map so Compose deployments can override them.

## Compose

```bash
docker compose up -d --build
docker compose ps
curl -fsS http://localhost/health
curl -fsS http://localhost/health/ready
```

Use the configured Nginx port when it differs from 80.

Sources are not bind-mounted. Backend, worker and scheduler build from the same
backend source directory, so shared backend changes require updating all three.
For a release that also changes the frontend:

```bash
docker compose build backend frontend worker scheduler
docker compose up -d --force-recreate --wait backend frontend worker scheduler
```

For frontend-only changes, rebuild and recreate only the frontend. After
container replacement, verify Nginx routing; reload Nginx if it retains old
upstream addresses. Healthy containers and HTTP 200 verify availability, not
successful execution of the user's business request.

## Migrations

```bash
docker compose run --rm --no-deps backend alembic heads
docker compose run --rm --no-deps backend alembic current
```

Use the newly built backend image to inspect migration files and the database
revision. If an upgrade is required, ensure a single head and back up Postgres
before applying it, then start the new application containers:

```bash
docker compose run --rm --no-deps backend alembic upgrade head
```

These one-off commands require the database to be running. For local development,
use the configured backend virtualenv and database connection. Application
rollback should retain compatible schema; migration downgrade does not undo
business writes.

## Ops checklist

| Symptom | Likely cause |
| --- | --- |
| UI ok, no notifications | Worker down |
| AI always stub | `LLM_*` empty or wrong |
| CORS / blank API on :3000 | Use Nginx entry, or set `NEXT_PUBLIC_API_BASE_URL` |
| "生成进行中" stuck | Call stop / `active-generation` reclaim |

## Seed

`make seed` creates demo users from `SEED_*_PASSWORD`. Do not use defaults on shared hosts.


## Database documentation and deployment state

Use `mcp/database/README.md` and the
[database skill](../project-agent-database/SKILL.md) to locate schema details and
known drift before a schema-changing release. The collection date in
`docs/database/` is not the current Alembic revision or proof of deployment.

Documentation/skill-only updates need no image rebuild or migration. Backend
runtime tools are code under `backend/app/agents/`, not loaded from `mcp/skills`.
For backend-only runtime changes, rebuild backend, worker and scheduler together;
verify tool imports/contract as well as service health when the tools changed.
After an actual schema migration, update the affected reference files using
verified metadata and retain the distinction between observed and pending schema.
