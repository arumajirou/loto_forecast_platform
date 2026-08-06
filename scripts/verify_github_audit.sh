#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TARGET_REPO="${GITHUB_AUDIT_REPO:-arumajirou/loto_forecast_platform}"
OUTPUT_ROOT="${GITHUB_AUDIT_VERIFY_OUTPUT_ROOT:-${REPO_ROOT}/artifacts/github-audit-verify}"
RUN_LIVE="${GITHUB_AUDIT_LIVE:-0}"

cd "${REPO_ROOT}"

if ! command -v uv >/dev/null 2>&1; then
  printf 'ERROR: uv is required for the repository verification lane.\n' >&2
  exit 127
fi

printf '=== GitHub audit focused verification ===\n'
printf 'REPO_ROOT=%s\nTARGET_REPO=%s\nRUN_LIVE=%s\n' \
  "${REPO_ROOT}" "${TARGET_REPO}" "${RUN_LIVE}"

uv run python -m ruff format --check \
  src/loto/github_audit \
  tests/test_github_audit.py

uv run python -m ruff check \
  src/loto/github_audit \
  tests/test_github_audit.py

uv run python -m compileall -q \
  src/loto/github_audit \
  tests/test_github_audit.py

uv run python -m pytest -q tests/test_github_audit.py
uv run loto-github-audit --self-test

if [[ "${RUN_LIVE}" == "1" ]]; then
  gh auth status --hostname github.com
  mkdir -p "${OUTPUT_ROOT}"
  uv run loto-github-audit \
    --repo "${TARGET_REPO}" \
    --output-root "${OUTPUT_ROOT}" \
    --max-items 100 \
    --max-action-runs 25 \
    --max-run-jobs 10 \
    --max-pr-details 10 \
    --max-issue-details 10
fi

printf 'VERIFICATION_STATUS=PASS\n'
