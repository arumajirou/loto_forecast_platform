#!/usr/bin/env bash

set -Eeuo pipefail

ROOT="$(
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." &&
  pwd
)"

PYTHON="$ROOT/environments/granite-ttm/.venv/bin/python"

SITE_PACKAGES="$(
  "$PYTHON" - <<'PY'
import site
print(site.getsitepackages()[0])
PY
)"

NVIDIA_LIBS="$(
  find "$SITE_PACKAGES/nvidia" \
    -type d \
    -name lib \
    -print \
    2>/dev/null \
  | sort \
  | paste -sd:
)"

if [[ -z "$NVIDIA_LIBS" ]]; then
  echo "BLOCKED: NVIDIA package libraries not found" >&2
  exit 2
fi

export LD_LIBRARY_PATH="$NVIDIA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec "$PYTHON" "$@"
