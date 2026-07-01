# ===================================================================
# FDE AI Platform — Makefile
# ===================================================================

.PHONY: help install dev dev-down test lint format typecheck \
        clean docker-up docker-down docker-logs pre-commit \
        cov cov-html cov-fail verify deploy-test docs

.DEFAULT_GOAL := help

VENV     := .venv
PYTHON   := $(VENV)/bin/python
PIP      := $(VENV)/bin/pip
PYTEST   := $(VENV)/bin/pytest
RUFF     := $(VENV)/bin/ruff
BLACK    := $(VENV)/bin/black
MYPY     := $(VENV)/bin/mypy
PRE_COMMIT := $(VENV)/bin/pre-commit

# ═══════════════════════════════════════════════════════════════════
# Help
# ═══════════════════════════════════════════════════════════════════

help:  ## Show this help
	@grep -E '^[a-zA-Z_.-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ═══════════════════════════════════════════════════════════════════
# Setup & Install
# ═══════════════════════════════════════════════════════════════════

install: $(VENV)  ## Create venv and install all dev dependencies
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev]"
	$(PRE_COMMIT) install
	@echo "✅ Installation complete"

$(VENV):
	python3 -m venv $(VENV)

install-all: install  ## Install ALL optional dependencies (heavy)
	$(PIP) install -e ".[router,rag,governance,observability,analysis,data,dev]"

# ═══════════════════════════════════════════════════════════════════
# Development Services
# ═══════════════════════════════════════════════════════════════════

docker-up:  ## Start Docker dev services (postgres, redis, qdrant, minio)
	docker compose -f docker-compose.dev.yml up -d
	@echo "✅ Dev services started"

docker-down:  ## Stop Docker dev services
	docker compose -f docker-compose.dev.yml down
	@echo "✅ Dev services stopped"

docker-logs:  ## Tail Docker dev service logs
	docker compose -f docker-compose.dev.yml logs -f

dev: docker-up  ## Full dev environment: Docker + services
	@echo "🚀 Dev environment ready"
	@echo "  PostgreSQL : postgres://fde:fde_dev_2026@localhost:5432/fde_platform"
	@echo "  Redis      : redis://localhost:6379"
	@echo "  Qdrant     : http://localhost:6333"
	@echo "  MinIO      : http://localhost:9001 (console)"

deploy-test:  ## Deploy to test server (configure FDE_TEST_SERVER and FDE_SSH_KEY)
	@test -n "$(FDE_TEST_SERVER)" || (echo "ERROR: Set FDE_TEST_SERVER=user@host" && exit 1)
	@test -n "$(FDE_SSH_KEY)" || (echo "ERROR: Set FDE_SSH_KEY=/path/to/key" && exit 1)
	@echo "Deploying to $(FDE_TEST_SERVER)..."
	rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
		--exclude '.mypy_cache' --exclude '.pytest_cache' --exclude '.ruff_cache' \
		--exclude 'htmlcov' --exclude '*.egg-info' \
		-e "ssh -i $(FDE_SSH_KEY) -o StrictHostKeyChecking=no" \
		./ $(FDE_TEST_SERVER):~/fde-ai-platform/
	ssh -i $(FDE_SSH_KEY) -o StrictHostKeyChecking=no $(FDE_TEST_SERVER) \
		"cd ~/fde-ai-platform && pip install -e '.[dev]'"
	@echo "Deployed to test server"

# ═══════════════════════════════════════════════════════════════════
# Code Quality
# ═══════════════════════════════════════════════════════════════════

lint:  ## Run ruff linter
	$(RUFF) check .

lint-fix:  ## Auto-fix lint issues
	$(RUFF) check . --fix

format:  ## Format code with Black
	$(BLACK) .

format-check:  ## Check formatting without changes
	$(BLACK) --check .

typecheck:  ## Run mypy type checking (strict)
	$(MYPY) conftest.py shared/ agents/ tests/

pre-commit:  ## Run all pre-commit hooks
	$(PRE_COMMIT) run --all-files

verify: format-check lint typecheck  ## Full static analysis gate

# ═══════════════════════════════════════════════════════════════════
# Testing
# ═══════════════════════════════════════════════════════════════════

test:  ## Run all tests
	$(PYTEST) -v

test-unit:  ## Run unit tests only
	$(PYTEST) -v -m "unit"

test-integration:  ## Run integration tests only
	$(PYTEST) -v -m "integration"

test-cov:  ## Run tests with coverage report
	$(PYTEST) --cov --cov-report=term-missing

cov-html:  ## Generate HTML coverage report
	$(PYTEST) --cov --cov-report=html
	@echo "📊 Coverage report: file://$$(pwd)/htmlcov/index.html"

cov-fail:  ## Run tests and fail under coverage threshold
	$(PYTEST) --cov --cov-fail-under=80

# ═══════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════

clean:  ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml
	@echo "✅ Cleaned"

clean-all: clean  ## Clean everything including venv
	rm -rf $(VENV)
	@echo "✅ All cleaned"

docs:  ## Serve API docs locally
	@echo "📖 API docs will be available at http://localhost:8000/docs"
	@echo "Run: make dev and then start the gateway service"