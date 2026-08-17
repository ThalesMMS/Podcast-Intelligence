SHELL := /bin/bash

.PHONY: help up down logs migrate seed check test lint format format-check backend-dev worker-dev frontend-dev mcp-dev smoke zip

help:
	@echo "Targets: up down logs migrate seed check test lint format format-check backend-dev worker-dev frontend-dev mcp-dev smoke zip"

up:
	docker compose up --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m podcast_intelligence.cli seed-demo

check: format-check lint test

test:
	cd backend && uv run pytest
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run mypy src
	cd frontend && npm run lint && npm run typecheck

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

format-check:
	cd backend && uv run ruff format --check .
	cd frontend && npm run format:check

backend-dev:
	cd backend && uv run uvicorn podcast_intelligence.main:app --reload --port 8000

worker-dev:
	cd backend && uv run celery -A podcast_intelligence.worker.celery_app:celery_app worker --loglevel=INFO

frontend-dev:
	cd frontend && npm run dev

mcp-dev:
	cd backend && uv run python -m podcast_intelligence.mcp_server

smoke:
	./scripts/smoke_test.sh

zip:
	git archive --format=zip --prefix=podcast-intelligence/ --output=../podcast-intelligence.zip HEAD
