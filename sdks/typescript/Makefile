SHELL := /bin/bash

.PHONY: help install install-no-frozen speakeasy-install generate overlay-test name-check generate-check lint typecheck test build release-check publish-dry-run publish clean

help:
	@echo "TypeScript SDK Makefile targets"
	@echo "  make install            - install dependencies (frozen lockfile)"
	@echo "  make speakeasy-install  - download pinned Speakeasy CLI"
	@echo "  make generate           - generate client into src/generated"
	@echo "  make overlay-test       - run Python tests for method-name overlay generator"
	@echo "  make name-check         - verify generated method names are ergonomic"
	@echo "  make generate-check     - regenerate and verify src/generated has no diffs"
	@echo "  make lint               - run ESLint"
	@echo "  make typecheck          - run tsc --noEmit"
	@echo "  make test               - run Vitest"
	@echo "  make build              - build package with tsup"
	@echo "  make release-check      - run publish gate checks"
	@echo "  make publish-dry-run    - run npm publish dry-run"
	@echo "  make publish            - publish package to npm"

install:
	pnpm install --frozen-lockfile

install-no-frozen:
	pnpm install

