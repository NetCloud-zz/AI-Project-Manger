# Backend — AI 项目管理 Agent

FastAPI service that owns every business fact (owners, due dates, task/project
status, permissions). The LLM layer only summarises and suggests; it never writes
authoritative data.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp ../.env.example ../.env      # then fill in what you need
alembic upgrade head
python -m app.scripts.seed      # admin / executive / owner / member
uvicorn app.main:app --reload --port 8000
```

- Health: <http://localhost:8000/health>
- Auth login: `POST /api/v1/auth/login`
- Current user: `GET /api/v1/me` (Bearer token)
- OpenAPI docs: <http://localhost:8000/docs>

## Layout

| Path                | Responsibility                                        |
| ------------------- | ----------------------------------------------------- |
| `app/api/`          | HTTP routes (`health.py`, `v1/`)                       |
| `app/core/`         | config, logging, database, redis, middleware, security, auth, deps |
| `app/models/`       | SQLAlchemy ORM models (Alembic autogenerate source)    |
| `app/schemas/`      | Pydantic request/response models                       |
| `app/repositories/` | data access, one module per aggregate                  |
| `app/services/`     | business rules — due date, delay, status transitions   |
| `app/agents/`       | LLM prompt orchestration (Phase 6+)                    |
| `app/llm/`          | LLM gateway client and provider abstraction (Phase 6)  |
| `app/integrations/` | WeCom and other external channels (Phase 10)           |
| `app/workers/`      | Celery app, scheduled tracking jobs (Phase 5)          |
| `alembic/`          | migration environment and versions                     |
| `tests/`            | pytest suite                                           |

## Commands

```bash
ruff check .            # lint
ruff format .           # format
mypy app                # type check
pytest                  # unit tests (no infrastructure required)
pytest -m integration   # requires live PostgreSQL + Redis

alembic revision --autogenerate -m "add projects"
alembic upgrade head
```

Unit tests must not need PostgreSQL or Redis. Anything that does belongs behind
the `integration` marker.
