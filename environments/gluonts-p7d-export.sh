#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${1:?usage: $0 <P7C_ORCHESTRATION_ROOT> [ARCHIVE.zip]}"
ARCHIVE="${2:-${RUN_ROOT%/}.zip}"

if [[ ! -d "${RUN_ROOT}" ]]; then
  echo "P7D_INPUT_MISSING=${RUN_ROOT}" >&2
  exit 2
fi

if command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run --project "${ROOT}" python)
elif python3 -c 'import pydantic' >/dev/null 2>&1; then
  PYTHON=(python3)
else
  echo "P7D_BLOCKED=no Python interpreter with Pydantic" >&2
  exit 2
fi

PYTHONPATH="${ROOT}/src" \
"${PYTHON[@]}" -m loto.adapters.gluonts.p7d_cli export \
  --run-root "${RUN_ROOT}" \
  --archive "${ARCHIVE}"

PYTHONPATH="${ROOT}/src" \
"${PYTHON[@]}" -m loto.adapters.gluonts.p7d_cli verify \
  --archive "${ARCHIVE}"

printf '%s\n' "P7D_RUN_ROOT=${RUN_ROOT}"
printf '%s\n' "P7D_ARCHIVE=${ARCHIVE}"
printf '%s\n' "P7D_ARCHIVE_SHA256_FILE=${ARCHIVE}.sha256"
