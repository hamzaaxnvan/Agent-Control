.PHONY: help test lint lint-fix typecheck check build

PACKAGE_DIR := $(notdir $(abspath $(CURDIR)))
COVERAGE_XML := ../../../coverage-evaluators-$(PACKAGE_DIR).xml

help:
	@echo "Agent Control contrib evaluator template"
	@echo ""
	@echo "  make test       - run pytest"
	@echo "  make lint       - run ruff check"
	@echo "  make lint-fix   - run ruff check --fix"
	@echo "  make typecheck  - run mypy"
	@echo "  make check      - run lint, typecheck, and tests"
	@echo "  make build      - build package"

