PYTHON ?= python3
NPM ?= npm

.PHONY: ensure-fixtures test test-backend test-frontend test-e2e dev-backend dev-frontend install-backend install-frontend

ensure-fixtures:
	$(PYTHON) scripts/check_fixtures.py

test: ensure-fixtures test-backend test-frontend

test-backend: ensure-fixtures
	$(PYTHON) -m pytest tests/backend

test-frontend:
	cd frontend && $(NPM) test -- --run

test-e2e:
	cd frontend && $(NPM) run test:e2e

dev-backend: ensure-fixtures
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && $(NPM) run dev -- --host 0.0.0.0

install-backend:
	$(PYTHON) -m pip install -e ".[dev]"

install-frontend:
	cd frontend && $(NPM) install
