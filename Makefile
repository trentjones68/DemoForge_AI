.DEFAULT_GOAL := help
SUPABASE_CLI ?= supabase
.PHONY: help install db-up db-down supabase-up supabase-down web api migrate lint typecheck test check build smoke

help:
	@printf '%s\n' 'install  Locked npm and Python installs' 'db-up/db-down  Start/stop Compose Postgres' 'supabase-up/supabase-down  Start/stop the full local Supabase stack' 'web/api  Run one development service per terminal' 'migrate  Upgrade the configured local database' 'check  Lint, typecheck and test' 'build  Build the web app' 'smoke  Check running web, API and database'

install:
	npm ci
	uv sync --locked

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

supabase-up:
	$(SUPABASE_CLI) start

supabase-down:
	$(SUPABASE_CLI) stop

web:
	npm run dev --workspace @demoforge/web -- --hostname 127.0.0.1

api:
	uv run --locked uvicorn demoforge_api.main:create_app --factory --app-dir services/api --reload

migrate:
	uv run --locked alembic upgrade head

lint:
	npm run lint --workspace @demoforge/web
	uv run --locked ruff check .
	uv run --locked ruff format --check .

typecheck:
	npm run typecheck --workspace @demoforge/web
	uv run --locked mypy

test:
	uv run --locked pytest

check: lint typecheck test

build:
	npm run build --workspace @demoforge/web

smoke:
	uv run --locked python tests/smoke.py
