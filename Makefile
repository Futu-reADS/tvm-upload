# Makefile for TVM Upload System
# Simplifies common development tasks

.PHONY: help install install-dev install-dev-tools test test-fast test-unit test-integration test-e2e test-all test-coverage test-manual clean clean-test clean-all lint format check run run-test-config deploy-install deploy-uninstall deploy-verify deploy-health

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)TVM Upload System - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Setup:$(NC)"
	@echo "  make install           Install in production mode"
	@echo "  make install-dev       Install with test dependencies"
	@echo "  make install-dev-tools Install linters, formatters & pre-commit hooks"
	@echo ""
	@echo "$(YELLOW)What Gets Installed:$(NC)"
	@echo "  Package         | install | install-dev | install-dev-tools"
	@echo "  ----------------|---------|-------------|------------------"
	@echo "  watchdog        |    ✅    |      ✅      |        ❌"
	@echo "  boto3           |    ✅    |      ✅      |        ❌"
	@echo "  pyyaml          |    ✅    |      ✅      |        ❌"
	@echo "  pytest          |    ❌    |      ✅      |        ❌"
	@echo "  pytest-cov      |    ❌    |      ✅      |        ❌"
	@echo "  pytest-mock     |    ❌    |      ✅      |        ❌"
	@echo "  black           |    ❌    |      ❌      |        ✅"
	@echo "  flake8          |    ❌    |      ❌      |        ✅"
	@echo "  pylint          |    ❌    |      ❌      |        ✅"
	@echo "  isort           |    ❌    |      ❌      |        ✅"
	@echo "  pre-commit      |    ❌    |      ❌      |        ✅"
	@echo "  pre-commit hooks|    ❌    |      ❌      |        ✅"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  make test              Run unit + integration tests (default, no e2e)"
	@echo "  make test-fast         Run unit tests only (fastest, ~5 sec)"
	@echo "  make test-unit         Run unit tests with verbose output"
	@echo "  make test-integration  Run integration tests"
	@echo "  make test-e2e          Run E2E tests (AWS_PROFILE=china)"
	@echo "  make test-all          Run ALL tests including E2E (AWS_PROFILE=china)"
	@echo "  make test-coverage     Run tests with HTML coverage report"
	@echo "  make test-manual       Run manual test scenarios (~24 min)"
	@echo ""
	@echo "$(GREEN)Code Quality:$(NC)"
	@echo "  make lint              Run linters (flake8, pylint)"
	@echo "  make format            Format code with black"
	@echo "  make check             Run all checks (lint + format check)"
	@echo ""
	@echo "$(GREEN)Running:$(NC)"
	@echo "  make run               Run the application with example config"
	@echo "  make run-test-config   Test configuration validity"
	@echo ""
	@echo "$(GREEN)Cleanup:$(NC)"
	@echo "  make clean             Remove Python cache files"
	@echo "  make clean-test        Remove test artifacts and coverage"
	@echo "  make clean-all         Remove all generated files"
	@echo ""
	@echo "$(GREEN)Deployment:$(NC)"
	@echo "  make deploy-verify     Verify deployment prerequisites"
	@echo "  make deploy-install    Install to production (requires sudo)"
	@echo "  make deploy-uninstall  Uninstall from production (requires sudo)"
	@echo "  make deploy-health     Run system health check (requires sudo)"
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make install-dev && make test-fast"
	@echo "  make test-all          # Runs all tests with AWS_PROFILE=china"
	@echo "  make test-e2e          # Runs E2E tests with AWS_PROFILE=china"
	@echo "  make deploy-verify && make deploy-install"

# ==================== Setup ====================

install:
	@echo "$(BLUE)Installing TVM Upload System (production)...$(NC)"
	@pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
	pip3 install -e .
	@echo "$(GREEN)✓ Installation complete (from pyproject.toml)$(NC)"

install-dev:
	@echo "$(BLUE)Installing TVM Upload System (development)...$(NC)"
	@pip3 install --upgrade pip setuptools wheel 2>/dev/null || true
	pip3 install -e ".[test]"
	@echo "$(GREEN)✓ Development installation complete (from pyproject.toml)$(NC)"

install-dev-tools:
	@echo "$(BLUE)Installing development tools (linters, formatters)...$(NC)"
	pip3 install -e ".[dev]"
	@echo ""
	@echo "$(BLUE)Installing pre-commit git hooks...$(NC)"
	@if [ -d .git ]; then \
		pre-commit install && \
		echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"; \
	else \
		echo "$(YELLOW)⚠ Not a git repository - skipping pre-commit hook installation$(NC)"; \
		echo "$(YELLOW)  Run 'pre-commit install' manually after git init$(NC)"; \
	fi
	@echo ""
	@echo "$(GREEN)✓ Development tools installed (from pyproject.toml)$(NC)"
	@echo "$(YELLOW)Tools installed: black, flake8, pylint, isort, pre-commit$(NC)"

# ==================== Testing ====================

test:
	@echo "$(BLUE)Running unit + integration tests...$(NC)"
	pytest tests/unit tests/integration -v -m "not e2e"
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-fast:
	@echo "$(BLUE)Running unit tests (fast)...$(NC)"
	pytest tests/unit -v -m "not e2e"
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-unit:
	@echo "$(BLUE)Running unit tests with verbose output...$(NC)"
	pytest tests/unit -vv -s
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration:
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration -v
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-e2e:
	@echo "$(BLUE)Running E2E tests (requires AWS credentials)...$(NC)"
	@echo "$(YELLOW)Using AWS_PROFILE=china (default for this project)$(NC)"
	AWS_PROFILE=china pytest tests/e2e -m e2e -v
	@echo "$(GREEN)✓ E2E tests complete$(NC)"

test-all:
	@echo "$(BLUE)Running ALL tests (unit + integration + E2E)...$(NC)"
	@echo "$(YELLOW)Using AWS_PROFILE=china (default for this project)$(NC)"
	AWS_PROFILE=china pytest tests/unit tests/integration tests/e2e -v
	@echo "$(GREEN)✓ All tests complete$(NC)"

test-coverage:
	@echo "$(BLUE)Running tests with coverage report...$(NC)"
	pytest tests/unit tests/integration tests/e2e --cov=src --cov-report=html --cov-report=term-missing --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated$(NC)"
	@echo "$(YELLOW)View HTML report: open htmlcov/index.html$(NC)"

test-manual:
	@echo "$(BLUE)Running manual test scenarios...$(NC)"
	@echo "$(YELLOW)This runs 17 automated manual test scenarios (~24 min)$(NC)"
	./scripts/testing/run_manual_tests.sh
	@echo "$(GREEN)✓ Manual tests complete$(NC)"

# ==================== Code Quality ====================

lint:
	@echo "$(BLUE)Running code linters...$(NC)"
	@MISSING=""; \
	if ! command -v flake8 > /dev/null 2>&1; then \
		echo "$(YELLOW)⚠ flake8 not installed (skipping)$(NC)"; \
		MISSING="$$MISSING flake8"; \
	else \
		echo "$(YELLOW)Running flake8...$(NC)"; \
		flake8 src/ tests/ --max-line-length=100 --exclude=venv,build,dist,*.egg-info --show-source --statistics || true; \
	fi; \
	echo ""; \
	if ! command -v pylint > /dev/null 2>&1; then \
		echo "$(YELLOW)⚠ pylint not installed (skipping)$(NC)"; \
		MISSING="$$MISSING pylint"; \
	else \
		echo "$(YELLOW)Running pylint...$(NC)"; \
		pylint src/ --max-line-length=100 --disable=C0103,C0114,R0913,R0914 || true; \
	fi; \
	if [ -n "$$MISSING" ]; then \
		echo ""; \
		echo "$(YELLOW)To install missing tools: pip3 install$$MISSING$(NC)"; \
		echo "$(YELLOW)Or install all dev tools: make install-dev-tools$(NC)"; \
	fi
	@echo "$(GREEN)✓ Linting complete$(NC)"

format:
	@echo "$(BLUE)Formatting code with black...$(NC)"
	@if ! command -v black > /dev/null 2>&1; then \
		echo "$(RED)Error: black not installed$(NC)"; \
		echo "$(YELLOW)Install with: pip3 install black$(NC)"; \
		echo "$(YELLOW)Or install all dev tools: make install-dev-tools$(NC)"; \
		exit 1; \
	fi
	black src/ tests/ --line-length=100
	@echo "$(GREEN)✓ Code formatting complete$(NC)"

check: lint
	@echo "$(BLUE)Running format check...$(NC)"
	@if ! command -v black > /dev/null 2>&1; then \
		echo "$(YELLOW)⚠ black not installed (skipping format check)$(NC)"; \
		echo "$(YELLOW)Install with: make install-dev-tools$(NC)"; \
	else \
		black src/ tests/ --line-length=100 --check || true; \
	fi
	@echo "$(GREEN)✓ All checks complete$(NC)"

# ==================== Running ====================

run:
	@echo "$(BLUE)Running TVM Upload System...$(NC)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(RED)Error: config/config.yaml not found$(NC)"; \
		echo "$(YELLOW)Copy config/config.yaml.example to config/config.yaml and customize$(NC)"; \
		exit 1; \
	fi
	python3 src/main.py --config config/config.yaml --log-level INFO

run-test-config:
	@echo "$(BLUE)Testing configuration...$(NC)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(RED)Error: config/config.yaml not found$(NC)"; \
		echo "$(YELLOW)Copy config/config.yaml.example to config/config.yaml and customize$(NC)"; \
		exit 1; \
	fi
	python3 src/main.py --config config/config.yaml --test-config
	@echo "$(GREEN)✓ Configuration is valid$(NC)"

# ==================== Cleanup ====================

clean:
	@echo "$(BLUE)Cleaning Python cache files...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Python cache cleaned$(NC)"

clean-test:
	@echo "$(BLUE)Cleaning test artifacts...$(NC)"
	rm -rf .pytest_cache/ .coverage htmlcov/ 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Test artifacts cleaned$(NC)"

clean-all: clean clean-test
	@echo "$(BLUE)Cleaning all generated files...$(NC)"
	rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true
	rm -rf venv/ env/ ENV/ 2>/dev/null || true
	@echo "$(GREEN)✓ All generated files cleaned$(NC)"

# ==================== Deployment Helpers ====================

.PHONY: deploy-install deploy-uninstall deploy-verify deploy-health

deploy-install:
	@echo "$(BLUE)Installing TVM Upload System to production...$(NC)"
	@echo "$(YELLOW)This requires sudo privileges$(NC)"
	sudo ./scripts/deployment/install.sh

deploy-uninstall:
	@echo "$(BLUE)Uninstalling TVM Upload System...$(NC)"
	@echo "$(YELLOW)This requires sudo privileges$(NC)"
	sudo ./scripts/deployment/uninstall.sh

deploy-verify:
	@echo "$(BLUE)Verifying deployment prerequisites...$(NC)"
	./scripts/deployment/verify_deployment.sh

deploy-health:
	@echo "$(BLUE)Running health check...$(NC)"
	@echo "$(YELLOW)This requires sudo privileges$(NC)"
	sudo ./scripts/deployment/health_check.sh

# ==================== Development Helpers ====================

.PHONY: dev-setup dev-test dev-watch

dev-setup: install-dev
	@echo "$(BLUE)Setting up development environment...$(NC)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(YELLOW)Creating config.yaml from example...$(NC)"; \
		cp config/config.yaml.example config/config.yaml; \
		echo "$(GREEN)✓ Config file created. Please customize it.$(NC)"; \
	fi
	@echo "$(GREEN)✓ Development environment ready$(NC)"
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  1. Edit config/config.yaml"
	@echo "  2. Run: make test-fast"
	@echo "  3. Run: make run-test-config"

dev-test: test-fast
	@echo "$(GREEN)✓ Quick development test complete$(NC)"

# ==================== Info ====================

.PHONY: info version

info:
	@echo "$(BLUE)TVM Upload System Information$(NC)"
	@echo ""
	@echo "Version:     2.1.0"
	@echo "Python:      $$(python3 --version 2>&1)"
	@echo "Pytest:      $$(pytest --version 2>&1 | head -1)"
	@echo "Pip:         $$(pip --version 2>&1)"
	@echo ""
	@echo "$(BLUE)Project Structure:$(NC)"
	@echo "  Source:        src/"
	@echo "  Tests:         tests/ (399 total tests)"
	@echo "  Config:        config/"
	@echo "  Scripts:       scripts/"
	@echo "  Docs:          docs/"
	@echo ""
	@echo "$(BLUE)Test Breakdown:$(NC)"
	@echo "  Unit:          249 tests (~5 sec)"
	@echo "  Integration:   90 tests (~35 sec)"
	@echo "  E2E:           60 tests (~7.5 min)"
	@echo "  Manual:        17 scenarios (~24 min)"

version:
	@echo "TVM Upload System v2.1.0"
	@python3 src/main.py --config config/config.yaml.example --test-config 2>/dev/null | grep -i version || echo "v2.1.0"
