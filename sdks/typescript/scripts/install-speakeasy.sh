#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BIN_DIR="${SDK_ROOT}/.speakeasy/bin"
BIN_PATH="${BIN_DIR}/speakeasy"
WORKFLOW_FILE="${SDK_ROOT}/.speakeasy/workflow.yaml"

if [[ -z "${SPEAKEASY_VERSION:-}" && -f "${WORKFLOW_FILE}" ]]; then
  SPEAKEASY_VERSION="$(awk '/^speakeasyVersion:/ {print $2; exit}' "${WORKFLOW_FILE}" | tr -d "\"'")"
fi

SPEAKEASY_VERSION="${SPEAKEASY_VERSION:-1.721.5-rc.0}"
if [[ "${SPEAKEASY_VERSION}" != v* ]]; then
  SPEAKEASY_VERSION="v${SPEAKEASY_VERSION}"
fi

if [[ -x "${BIN_PATH}" ]]; then
  CURRENT_VERSION="$("${BIN_PATH}" --version | head -n1 | awk '{print $NF}' || true)"
  DESIRED_WITHOUT_V="${SPEAKEASY_VERSION#v}"

  if [[ "${CURRENT_VERSION}" == "${SPEAKEASY_VERSION}" || "${CURRENT_VERSION}" == "${DESIRED_WITHOUT_V}" ]]; then
    echo "Speakeasy CLI already present at ${BIN_PATH}"
    exit 0
  fi
