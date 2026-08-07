#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
cd "$ROOT"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/harness/quality-gate/${RUN_ID}"
mkdir -p "$OUT"

finish() {
  rc=$?
  set +e
  printf '%s\n' "$rc" > "$OUT/exit_code.txt"
  if [ "$rc" -eq 0 ]; then
    printf 'VERIFIED\n' > "$OUT/status.txt"
  else
    printf 'FAILED\n' > "$OUT/status.txt"
  fi
  (
    cd "$OUT" || exit 0
    find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 \
      | sort -z | xargs -0 sha256sum > SHA256SUMS
  )
  echo "HARNESS_QUALITY_GATE=$(cat "$OUT/status.txt")"
  echo "output=$OUT"
  exit "$rc"
}
trap finish EXIT

exec > >(tee "$OUT/quality-gate.log") 2>&1
uv run --extra harness --extra dev ruff check src/loto/harness tests/harness
uv run --extra harness --extra dev mypy src/loto/harness
uv run --extra harness --extra dev pytest -q tests/harness
echo "QUALITY_COMMANDS=PASS"
