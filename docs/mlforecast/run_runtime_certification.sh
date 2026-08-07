#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
cd "$ROOT"

WHEEL="${1:-$ROOT/artifacts/mlforecast-wheel/mlforecast-1.1.0-py3-none-any.whl}"
OUTPUT_ROOT="${2:-$ROOT/artifacts/mlforecast-runtime-certification}"
BUNDLE_ROOT="${3:-$ROOT/artifacts/mlforecast-runtime-bundles}"
EXPECTED_SHA256="0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748"
WHEEL_URL="https://files.pythonhosted.org/packages/"
WHEEL_URL+="b2/9d/bf967c65a035d278302dff82ae739862a773fbd2a2344f258035d2df3136/"
WHEEL_URL+="mlforecast-1.1.0-py3-none-any.whl"
AUTO_DOWNLOAD="${MLFORECAST_AUTO_DOWNLOAD:-1}"

if ! command -v uv >/dev/null 2>&1; then
  printf 'BLOCKED: uv is not available in PATH\n' >&2
  exit 2
fi
if ! command -v sha256sum >/dev/null 2>&1; then
  printf 'BLOCKED: sha256sum is not available in PATH\n' >&2
  exit 2
fi
if [[ ! -f "$ROOT/uv.lock" ]]; then
  printf 'BLOCKED: uv.lock not found at repository root: %s\n' "$ROOT" >&2
  exit 2
fi

TEMP_FILES=()
cleanup() {
  local path
  for path in "${TEMP_FILES[@]}"; do
    rm -f -- "$path"
  done
  return 0
}
trap cleanup EXIT

if [[ ! -f "$WHEEL" ]]; then
  if [[ "$AUTO_DOWNLOAD" != "1" ]]; then
    printf 'BLOCKED: wheel not found and automatic download is disabled: %s\n' \
      "$WHEEL" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$WHEEL")"
  PARTIAL_WHEEL="${WHEEL}.partial.$$"
  TEMP_FILES+=("$PARTIAL_WHEEL")
  printf 'Downloading frozen MLForecast wheel from official PyPI storage...\n'
  if command -v curl >/dev/null 2>&1; then
    curl \
      --fail \
      --location \
      --proto '=https' \
      --tlsv1.2 \
      --retry 3 \
      --output "$PARTIAL_WHEEL" \
      "$WHEEL_URL"
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$WHEEL_URL" "$PARTIAL_WHEEL" <<'PY'
from pathlib import Path
import shutil
import sys
import urllib.request

url = sys.argv[1]
target = Path(sys.argv[2])
request = urllib.request.Request(url, headers={"User-Agent": "loto-mlforecast-certifier/1"})
with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
    shutil.copyfileobj(response, handle)
PY
  else
    printf 'BLOCKED: neither curl nor python3 is available for wheel download\n' >&2
    exit 2
  fi
  mv "$PARTIAL_WHEEL" "$WHEEL"
fi

ACTUAL_SHA256="$(sha256sum "$WHEEL" | awk '{print $1}')"
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  printf 'FAILED: wheel SHA-256 mismatch\nEXPECTED=%s\nACTUAL=%s\n' \
    "$EXPECTED_SHA256" "$ACTUAL_SHA256" >&2
  exit 3
fi

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

mkdir -p "$OUTPUT_ROOT" "$BUNDLE_ROOT"
BEFORE_RUNS="$(mktemp)"
AFTER_RUNS="$(mktemp)"
TEMP_FILES+=("$BEFORE_RUNS" "$AFTER_RUNS")

snapshot_runs() {
  find "$OUTPUT_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name 'mlforecast-runtime-*' \
    -printf '%f\n' \
    | sort
}

snapshot_runs > "$BEFORE_RUNS"
set +e
uv run \
  --frozen \
  --with "$WHEEL" \
  -- \
  python -m loto.mlforecast.certify \
  --wheel "$WHEEL" \
  --output-root "$OUTPUT_ROOT" \
  --seed 1 \
  --auto-trials 2
CERTIFICATION_STATUS=$?
set -e
snapshot_runs > "$AFTER_RUNS"

mapfile -t NEW_RUNS < <(comm -13 "$BEFORE_RUNS" "$AFTER_RUNS")
if [[ "${#NEW_RUNS[@]}" -ne 1 ]]; then
  printf 'FAILED: expected exactly one new certification run, observed=%s\n' \
    "${#NEW_RUNS[@]}" >&2
  exit 4
fi

RUN_ID="${NEW_RUNS[0]}"
if [[ ! "$RUN_ID" =~ ^mlforecast-runtime-[0-9]{8}-[0-9]{6}-[0-9]{6}$ ]]; then
  printf 'FAILED: invalid certification run id: %s\n' "$RUN_ID" >&2
  exit 4
fi
RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
ZIP_PATH="$BUNDLE_ROOT/$RUN_ID.zip"
ZIP_SHA256_PATH="$BUNDLE_ROOT/$RUN_ID.zip.sha256"
VERIFICATION_REPORT="$BUNDLE_ROOT/$RUN_ID.verification.json"

set +e
uv run \
  --frozen \
  -- \
  python -m loto.mlforecast.bundle \
  --run-dir "$RUN_DIR" \
  --output-dir "$BUNDLE_ROOT"
BUNDLE_STATUS=$?
set -e
if [[ "$BUNDLE_STATUS" -ne 0 ]]; then
  printf 'FAILED: runtime evidence bundling failed for %s\n' "$RUN_ID" >&2
  exit 5
fi

set +e
uv run \
  --frozen \
  -- \
  python -m loto.mlforecast.bundle \
  --verify-zip "$ZIP_PATH" \
  --sha256-file "$ZIP_SHA256_PATH" \
  --report "$VERIFICATION_REPORT"
VERIFY_STATUS=$?
set -e
if [[ "$VERIFY_STATUS" -ne 0 ]]; then
  printf 'FAILED: independent runtime bundle verification failed for %s\n' \
    "$RUN_ID" >&2
  exit 6
fi

printf 'RUN_ID=%s\n' "$RUN_ID"
printf 'RUN_DIR=%s\n' "$RUN_DIR"
printf 'BUNDLE=%s\n' "$ZIP_PATH"
printf 'BUNDLE_SHA256=%s\n' "$ZIP_SHA256_PATH"
printf 'BUNDLE_VERIFICATION_REPORT=%s\n' "$VERIFICATION_REPORT"
exit "$CERTIFICATION_STATUS"
