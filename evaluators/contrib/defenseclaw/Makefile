.PHONY: help sync test lint lint-fix typecheck check build

PACKAGE := agent-control-evaluator-defenseclaw

help:
	@echo "Agent Control Evaluator - DefenseClaw - Makefile commands"
	@echo "  make sync       - sync package dependencies"
	@echo "  make test       - run pytest"
	@echo "  make lint       - run ruff check"
	@echo "  make lint-fix   - run ruff check --fix"
	@echo "  make typecheck  - run mypy"
	@echo "  make check      - run tests, lint, and typecheck"
	@echo "  make build      - build package"

sync:
	uv sync
