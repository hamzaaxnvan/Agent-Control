#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
SPEAKEASY_BIN="${SDK_ROOT}/.speakeasy/bin/speakeasy"
SPEC_PATH="${OPENAPI_SPEC_PATH:-${SDK_ROOT}/../../server/.generated/openapi.json}"
OVERLAY_GENERATOR="${SCRIPT_DIR}/generate-method-names-overlay.py"
NORMALIZE_GENERATOR="${SCRIPT_DIR}/normalize_generated_sdk.py"
OVERLAY_PATH="${SDK_ROOT}/overlays/method-names.overlay.yaml"
TMP_OUTPUT_DIR="${SDK_ROOT}/.speakeasy/tmp-generated"
TMP_SPEC_PATH="${TMP_OUTPUT_DIR}/openapi.with-overrides.json"
GENERATED_DIR="${SDK_ROOT}/src/generated"

if [[ ! -x "${SPEAKEASY_BIN}" ]]; then
  echo "Speakeasy CLI not found at ${SPEAKEASY_BIN}. Run: make speakeasy-install" >&2
  exit 1
fi

if [[ ! -f "${SPEC_PATH}" ]]; then
  echo "OpenAPI spec not found at ${SPEC_PATH}. Generate it with: make openapi-spec" >&2
  exit 1
