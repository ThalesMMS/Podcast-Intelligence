SHELL := /bin/bash
PYTHON ?= python3
DESKTOP_TARGET ?=
SOURCE_ARCHIVE ?= ../Podcast-Intelligence-Desktop.zip

.PHONY: help format format-check lint typecheck test check smoke up down \
	desktop-check desktop-build source-zip clean

help:
	@printf '%s\n' \
	  'make check          - run backend and frontend quality gates' \
	  'make desktop-check  - add desktop Python and Rust checks' \
	  'make desktop-build  - build native desktop bundle for this host' \
	  'make source-zip     - create a clean deterministic source archive' \
	  'make up/down        - start or stop the Docker/server profile'

format:
	cd backend && uv run ruff format src tests
	cd frontend && npm run format
	cargo fmt --manifest-path frontend/src-tauri/Cargo.toml

format-check:
	cd backend && uv run ruff format --check src tests
	cd frontend && npm run format:check
	cargo fmt --manifest-path frontend/src-tauri/Cargo.toml -- --check

lint:
	cd backend && uv run ruff check src tests
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy src
	cd frontend && npm run typecheck

test:
	cd backend && uv run pytest
	cd frontend && npm test

check: format-check lint typecheck test

desktop-check:
	cd backend && uv run pytest tests/test_settings.py tests/test_local_object_store.py tests/test_retrieval.py
	cd frontend && npm run typecheck && npm test && npm run build
	cargo fmt --manifest-path frontend/src-tauri/Cargo.toml -- --check
	cargo check --manifest-path frontend/src-tauri/Cargo.toml

smoke:
	./scripts/smoke_test.sh

up:
	docker compose up -d --build --wait

down:
	docker compose down

desktop-build:
	@if [[ -n "$(DESKTOP_TARGET)" ]]; then \
		./scripts/build-desktop.sh "$(DESKTOP_TARGET)"; \
	else \
		./scripts/build-desktop.sh; \
	fi

source-zip:
	$(PYTHON) scripts/package-source.py --output "$(SOURCE_ARCHIVE)"

clean:
	rm -rf backend/build backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/coverage frontend/node_modules frontend/src-tauri/target
	rm -rf build
