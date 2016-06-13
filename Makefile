.PHONY: help sync openapi-spec openapi-spec-check test test-extras test-all contrib-verify scripts-test models-test test-models test-sdk lint lint-fix typecheck check build build-models build-server build-sdk publish publish-models publish-server publish-sdk hooks-install hooks-uninstall prepush evaluators-test evaluators-lint evaluators-lint-fix evaluators-typecheck evaluators-build contrib-test contrib-lint contrib-lint-fix contrib-typecheck contrib-build sdk-ts-generate sdk-ts-overlay-test sdk-ts-name-check sdk-ts-generate-check sdk-ts-build sdk-ts-test sdk-ts-lint sdk-ts-typecheck sdk-ts-release-check sdk-ts-publish-dry-run sdk-ts-publish telemetry-test telemetry-lint telemetry-lint-fix telemetry-typecheck telemetry-build telemetry-publish

# Workspace package names
PACK_MODELS := agent-control-models
PACK_SERVER := agent-control-server
PACK_SDK    := agent-control
PACK_ENGINE := agent-control-engine
PACK_TELEMETRY := agent-control-telemetry
PACK_EVALUATORS := agent-control-evaluators
OPENAPI_SPEC_PATH := server/.generated/openapi.json

# Directories
MODELS_DIR := models
SERVER_DIR := server
SDK_DIR    := sdks/python
TS_SDK_DIR := sdks/typescript
ENGINE_DIR := engine
TELEMETRY_DIR := telemetry
EVALUATORS_DIR := evaluators/builtin
CONTRIB_DIR := evaluators/contrib
UI_DIR := ui

define run-contrib-target
	@set -e; \
	packages=$$(uv run python scripts/contrib_packages.py names); \
	for package in $$packages; do \
		$(MAKE) -C $(CONTRIB_DIR)/$$package $(1); \
	done
endef

help:
	@echo "Agent Control - Makefile commands"
	@echo ""
	@echo "Setup:"
	@echo "  make sync            - uv sync all workspace packages at root (single .venv for all)"
	@echo ""
	@echo "Run:"
	@echo "  make server-<target> - forward to server targets (e.g., server-help, server-alembic-upgrade)"
	@echo "  make ui-<target>     - forward to UI targets (e.g., ui-help, ui-dev, ui-lint, ui-lint--fix)"
	@echo "  make openapi-spec    - generate runtime OpenAPI spec at $(OPENAPI_SPEC_PATH)"
	@echo "  make openapi-spec-check - verify OpenAPI generation succeeds"
	@echo ""
	@echo "Test:"
	@echo "  make test            - run tests for core packages and all discovered contrib evaluators"
	@echo "  make contrib-verify  - verify root contrib packaging contract wiring"
	@echo "  make scripts-test    - run root contrib packaging contract tests"
	@echo "  make models-test     - run shared model tests with coverage"
	@echo "  make test-extras     - run tests for all discovered contrib evaluators"
	@echo "  make test-all        - alias for make test"
	@echo "  make sdk-ts-test     - run TypeScript SDK tests"
	@echo ""
	@echo "Quality:"
	@echo "  make lint            - ruff check for all members"
	@echo "  make lint-fix        - ruff check --fix (auto-fix) for all members"
	@echo "  make typecheck       - mypy for all members"
	@echo "  make check           - run test, lint, and typecheck"
	@echo "  make sdk-ts-lint | sdk-ts-typecheck | sdk-ts-build | sdk-ts-generate | sdk-ts-overlay-test | sdk-ts-name-check"
	@echo "  make sdk-ts-release-check - run TypeScript SDK publish gate checks"
	@echo "  make sdk-ts-publish-dry-run - run npm publish dry-run for TypeScript SDK"
	@echo ""
	@echo "Build / Publish:"
	@echo "  make build           - build wheels for all members"
	@echo "  make publish         - publish all members (ensure credentials configured)"
	@echo "  make build-models | build-server | build-sdk"
	@echo "  make publish-models | publish-server | publish-sdk"
	@echo ""
	@echo "Git hooks:"
	@echo "  make hooks-install   - install repo-local git hooks (pre-push)"
	@echo "  make hooks-uninstall - restore default .git/hooks"
	@echo "  make prepush         - run pre-push checks locally"

# ---------------------------
# Setup
# ---------------------------

sync:
	uv sync --all-packages

# ---------------------------
# OpenAPI spec
# ---------------------------

openapi-spec:
	uv run --package $(PACK_SERVER) python server/openapi.py --output $(OPENAPI_SPEC_PATH)

openapi-spec-check: openapi-spec
	test -s $(OPENAPI_SPEC_PATH)

# ---------------------------
# Run
# ---------------------------

