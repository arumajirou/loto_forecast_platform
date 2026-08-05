#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P7B_OUT="${1:?usage: $0 <P7B_OUTPUT> [P7C_OUTPUT]}"
P7C_OUT="${2:-${P7B_OUT%/}-p7c}"

if [[ ! -d "${P7B_OUT}" ]]; then
  echo "P7C_INPUT_MISSING=${P7B_OUT}" >&2
  exit 2
fi

if command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run --project "${ROOT}" python)
elif python3 -c 'import pydantic' >/dev/null 2>&1; then
  PYTHON=(python3)
else
  echo "P7C_BLOCKED=no Python interpreter with Pydantic" >&2
  exit 2
fi

set +e
PYTHONPATH="${ROOT}/src" \
"${PYTHON[@]}" -m loto.adapters.gluonts.p7c_cli \
  --p7b-output "${P7B_OUT}" \
  --output-dir "${P7C_OUT}"
RC=$?
set -e

printf '%s\n' "P7C_RC=${RC}"
printf '%s\n' "P7C_INPUT=${P7B_OUT}"
printf '%s\n' "P7C_OUTPUT=${P7C_OUT}"
exit "${RC}"
