#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${1:?usage: $0 <P7D_ARCHIVE.zip> [OUTPUT_DIR]}"
OUTPUT_DIR="${2:-${ARCHIVE%.zip}-verified}"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "P7D_ARCHIVE_MISSING=${ARCHIVE}" >&2
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
"${PYTHON[@]}" -m loto.adapters.gluonts.p7d_cli verify \
  --archive "${ARCHIVE}" \
  --output-dir "${OUTPUT_DIR}"

printf '%s\n' "P7D_ARCHIVE=${ARCHIVE}"
printf '%s\n' "P7D_VERIFIED_OUTPUT=${OUTPUT_DIR}"
