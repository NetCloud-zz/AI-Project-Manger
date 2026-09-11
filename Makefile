SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND  := backend
FRONTEND := frontend
VENV     := $(BACKEND)/.venv
PY       := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
COMPOSE  := docker compose

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- bootstrap ---

.PHONY: env
env: ## Create .env from .env.example if absent
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

.PHONY: install
install: install-backend install-frontend ## Install all dependencies

.PHONY: install-backend
install-backend: ## Create the backend virtualenv and install dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e "./$(BACKEND)[dev]"

.PHONY: install-frontend
install-frontend: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

# ---------------------------------------------------------------------- dev ---

.PHONY: dev-backend
dev-backend: ## Run the backend with autoreload on :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: dev-frontend
dev-frontend: ## Run the Next.js dev server on :3000
	cd $(FRONTEND) && npm run dev

.PHONY: dev-worker
dev-worker: ## Run a Celery worker
	cd $(BACKEND) && .venv/bin/celery -A app.workers.celery_app:celery_app worker -l info

.PHONY: dev-beat
dev-beat: ## Run Celery Beat
	cd $(BACKEND) && .venv/bin/celery -A app.workers.celery_app:celery_app beat -l info

# ------------------------------------------------------------------ quality ---

.PHONY: fmt
fmt: ## Format backend code
	cd $(BACKEND) && .venv/bin/ruff format .
	cd $(BACKEND) && .venv/bin/ruff check --fix .

.PHONY: lint
lint: lint-backend lint-frontend ## Lint everything

.PHONY: lint-backend
lint-backend: ## Ruff + mypy
	cd $(BACKEND) && .venv/bin/ruff format --check .
	cd $(BACKEND) && .venv/bin/ruff check .
	cd $(BACKEND) && .venv/bin/mypy app

.PHONY: lint-frontend
lint-frontend: ## ESLint + tsc
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run typecheck

.PHONY: test
test: ## Run backend unit tests (minimal Stage-5 set)
	cd $(BACKEND) && .venv/bin/pytest

.PHONY: test-integration
test-integration: ## Integration tests (marker); requires live Postgres/Redis
	cd $(BACKEND) && .venv/bin/pytest -m integration

.PHONY: eval-list
eval-list: ## Show assistant eval cases (OPT-11 YAML; no live LLM)
	@sed -n '1,120p' $(BACKEND)/evals/cases.yaml

.PHONY: check
check: lint test ## Lint + unit tests

# ---------------------------------------------------------------- migrations ---

.PHONY: migrate
migrate: ## Apply all migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="add projects"
	@test -n "$(m)" || (echo 'usage: make migration m="add projects"'; exit 1)
	cd $(BACKEND) && .venv/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade: ## Roll back one migration
	cd $(BACKEND) && .venv/bin/alembic downgrade -1

# -------------------------------------------------------------------- docker ---

.PHONY: up
up: env ## Start the whole stack in the background
	$(COMPOSE) up -d --build

.PHONY: up-infra
up-infra: env ## Start only PostgreSQL and Redis (for local dev)
	$(COMPOSE) up -d postgres redis

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete its volumes (destroys data)
	$(COMPOSE) down -v

.PHONY: ps
ps: ## Show service state and health
	$(COMPOSE) ps

.PHONY: logs
logs: ## Tail logs: make logs s=backend
	$(COMPOSE) logs -f $(s)

.PHONY: build
build: ## Build all images
	$(COMPOSE) build

.PHONY: package
package: ## Build local source release tarball under dist/
	@mkdir -p dist
	@rm -f dist/project-agent-0.2.1.tar.gz
	@STAGE=$$(mktemp -d) && \
	NAME=project-agent-0.2.1 && \
	mkdir -p "$$STAGE/$$NAME" && \
	rsync -a \
	  --exclude='.git/' \
	  --exclude='.env' \
	  --exclude='.env.local' \
	  --exclude='.env.production' \
	  --exclude='.secrets/' \
	  --exclude='secrets/' \
	  --exclude='node_modules/' \
	  --exclude='.venv/' \
	  --exclude='venv/' \
	  --exclude='frontend/.next/' \
	  --exclude='**/__pycache__/' \
	  --exclude='.pytest_cache/' \
	  --exclude='.ruff_cache/' \
	  --exclude='.mypy_cache/' \
	  --exclude='dist/' \
	  --exclude='uploads/' \
	  --exclude='logs/' \
	  --exclude='tmp/' \
	  --exclude='.cursor/' \
	  --exclude='agent-transcripts/' \
	  --exclude='docs/qa/' \
	  --exclude='docs/ops/' \
	  --exclude='docs/SYSTEM_FIX_PLAN.md' \
	  --exclude='docs/MERGED_TEST_SUMMARY.md' \
	  --exclude='docs/TEST_REPORT.md' \
	  --exclude='docs/FULL_FUNCTION_TESTING_GUIDE.md' \
	  --exclude='*.dump' \
	  --exclude='*.sql.gz' \
	  ./ "$$STAGE/$$NAME/" && \
	test -f "$$STAGE/$$NAME/.env.example" && \
	! test -f "$$STAGE/$$NAME/.env" && \
	! test -d "$$STAGE/$$NAME/.secrets" && \
	tar -C "$$STAGE" -czf "dist/$$NAME.tar.gz" "$$NAME" && \
	rm -rf "$$STAGE" && \
	ls -lh "dist/$$NAME.tar.gz" && \
	sha256sum "dist/$$NAME.tar.gz" > "dist/$$NAME.tar.gz.sha256" && \
	cat "dist/$$NAME.tar.gz.sha256"

.PHONY: release-local
release-local: package build ## Package + rebuild all compose images
	$(COMPOSE) up -d --force-recreate
	@sleep 4
	@$(COMPOSE) ps
	@curl -fsS http://127.0.0.1:8080/health && echo
	@curl -sS http://127.0.0.1:8080/health/ready; echo

.PHONY: seed
seed: ## Seed default users (admin / executive / owner / member)
	cd $(BACKEND) && .venv/bin/python -m app.scripts.seed

.PHONY: health
health: ## Probe the backend health endpoints
	@curl -fsS http://localhost:8000/health && echo
	@curl -sS http://localhost:8000/health/ready && echo
