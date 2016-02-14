.PHONY: help test lint lint-fix typecheck build publish

TEST_DB ?= agent_control_test
TEST_SERVER_PORT ?= 18000
TEST_SERVER_HOST ?= 127.0.0.1
TEST_SERVER_URL := http://$(TEST_SERVER_HOST):$(TEST_SERVER_PORT)
TEST_DB_ENV := env -u AGENT_CONTROL_DB_URL -u DATABASE_URL -u DB_URL AGENT_CONTROL_DB_HOST=localhost AGENT_CONTROL_DB_PORT=5432 AGENT_CONTROL_DB_USER=agent_control AGENT_CONTROL_DB_PASSWORD=agent_control AGENT_CONTROL_DB_DATABASE=$(TEST_DB) AGENT_CONTROL_DB_DRIVER=psycopg

help:
	@echo "Agent Control SDK - Makefile commands"
	@echo ""
	@echo "Quality:"
	@echo "  make lint            - run ruff check (using root config)"
	@echo "  make lint-fix        - run ruff check --fix"
	@echo "  make typecheck       - run mypy (using root config)"
	@echo ""
	@echo "Test:"
