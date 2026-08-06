#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TARGET_REPO="${GITHUB_AUDIT_REPO:-arumajirou/loto_forecast_platform}"
OUTPUT_ROOT="${GITHUB_AUDIT_OUTPUT_ROOT:-${REPO_ROOT}/artifacts/github-audit}"
DEEP="${GITHUB_AUDIT_DEEP:-1}"

mkdir -p "${OUTPUT_ROOT}"

args=(
  --repo "${TARGET_REPO}"
  --output-root "${OUTPUT_ROOT}"
)
if [[ "${DEEP}" == "1" ]]; then
  args+=(--deep)
fi
args+=("$@")

printf 'REPO=%s\nOUTPUT_ROOT=%s\nDEEP=%s\n' "${TARGET_REPO}" "${OUTPUT_ROOT}" "${DEEP}"

if command -v uv >/dev/null 2>&1; then
  cd "${REPO_ROOT}"
  exec uv run loto-github-audit "${args[@]}"
fi

if command -v python3 >/dev/null 2>&1; then
  export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
  cd "${REPO_ROOT}"
  exec python3 -m loto.github_audit.cli "${args[@]}"
fi

printf 'ERROR: uv or python3 is required.\n' >&2
exit 127
