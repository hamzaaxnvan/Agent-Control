SHELL := /bin/bash

ALEMBIC := uv run --with alembic alembic -c alembic.ini

MSG ?= update
UP ?= head
DOWN ?= -1
SHOW ?= head
STAMP ?= head
AGENT_CONTROL_HOST ?= 0.0.0.0
AGENT_CONTROL_PORT ?= 8000
AGENT_CONTROL_DB_PORT ?= 5432
AGENT_CONTROL_DB_HOST_PORT ?= $(AGENT_CONTROL_DB_PORT)
AGENT_CONTROL_DOCKER_COMPOSE_PROJECT_NAME ?= $(notdir $(or $(PWD),$(CURDIR)))-dev

TEST_DB ?= agent_control_test
TEST_DB_ENV := env -u AGENT_CONTROL_DB_URL -u DATABASE_URL -u DB_URL AGENT_CONTROL_DB_HOST=localhost AGENT_CONTROL_DB_PORT=5432 AGENT_CONTROL_DB_USER=agent_control AGENT_CONTROL_DB_PASSWORD=agent_control AGENT_CONTROL_DB_DATABASE=$(TEST_DB) AGENT_CONTROL_DB_DRIVER=psycopg
.PHONY: help run start-dependencies test migrate alembic-migrate alembic-revision alembic-upgrade alembic-downgrade alembic-current alembic-history alembic-heads alembic-show alembic-stamp

help:
	@echo "Available targets:"
	@echo "  run                          - start FastAPI server (reload; honors AGENT_CONTROL_HOST/AGENT_CONTROL_PORT)"
	@echo "                                 local Postgres host mapping defaults to AGENT_CONTROL_DB_PORT"
	@echo "  start-dependencies           - docker compose up -d (start local dependencies; project=$(AGENT_CONTROL_DOCKER_COMPOSE_PROJECT_NAME))"
	@echo "  test                         - run server tests (uses $(TEST_DB_ENV))"
	@echo "  migrate                      - run database migrations (alembic upgrade head)"
	@echo "  alembic-migrate MSG='message'  - autogenerate alembic revision"
	@echo "  alembic-upgrade UP=head        - upgrade to revision"
	@echo "  alembic-downgrade DOWN=-1      - downgrade to revision"
	@echo "  alembic-current                - show current revision"
	@echo "  alembic-history                - show migration history"
	@echo "  alembic-heads                  - show heads"
	@echo "  alembic-show SHOW=<rev>        - show revision detail"
	@echo "  alembic-stamp STAMP=<rev>      - set head without running migrations"

migrate:
	@echo "Running database migrations..."
	$(ALEMBIC) upgrade head

