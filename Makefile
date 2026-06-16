.PHONY: install test test-cov demo demo-thermal lint typecheck clean help

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=agents --cov=tools --cov-report=term-missing --cov-report=html
	@echo "HTML coverage report written to htmlcov/index.html"

test-fast:
	pytest tests/ -x -q

# ── Examples ──────────────────────────────────────────────────────────────────

demo:
	python -m examples.run_synthetic_incident

demo-thermal:
	python -m examples.run_thermal_incident

# ── Code quality ──────────────────────────────────────────────────────────────

lint:
	ruff check agents/ tools/ examples/ tests/

typecheck:
	mypy agents/ tools/ --ignore-missing-imports

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean."

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  make install       Install package + dev dependencies"
	@echo "  make test          Run full test suite"
	@echo "  make test-cov      Run tests with HTML coverage report"
	@echo "  make test-fast     Run tests, stop on first failure"
	@echo "  make demo          Run latency incident example"
	@echo "  make demo-thermal  Run thermal throttling incident example"
	@echo "  make lint          Run ruff linter"
	@echo "  make typecheck     Run mypy type checker"
	@echo "  make clean         Remove build artifacts"
	@echo ""
