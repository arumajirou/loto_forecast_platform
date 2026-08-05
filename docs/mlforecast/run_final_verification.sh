#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$ROOT"

for command in git uv bash python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'FINAL_VERIFICATION_SETUP_ERROR: %s is unavailable\n' "$command" >&2
    exit 2
  fi
done

SCOPED_PATHS=(
  configs/mlforecast
  docs/mlforecast
  src/loto/mlforecast
  tests/mlforecast
  pyproject.toml
  uv.lock
)

HEAD_SHA="$(git rev-parse HEAD)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMITTED_AT="$(git show -s --format=%cI HEAD)"
if [[ "$BRANCH" == "HEAD" || -z "$BRANCH" ]]; then
  printf 'FINAL_VERIFICATION_SETUP_ERROR: detached HEAD is not allowed\n' >&2
  exit 2
fi
DIRTY="$(git status --porcelain -- "${SCOPED_PATHS[@]}")"
if [[ -n "$DIRTY" ]]; then
  printf 'FINAL_VERIFICATION_SETUP_ERROR: verification inputs are dirty\n%s\n' "$DIRTY" >&2
  exit 2
fi

OUTPUT_ROOT="${1:-$ROOT/artifacts/mlforecast-final-verification}"
SKIP_RUNTIME="${MLFORECAST_SKIP_RUNTIME:-0}"
RUN_ID="mlforecast-final-$(date -u +%Y%m%d-%H%M%S-%N)-${HEAD_SHA:0:12}"
RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
LOG_DIR="$RUN_DIR/logs"
STEPS_TSV="$RUN_DIR/STEPS.tsv"
mkdir -p "$LOG_DIR"
: > "$STEPS_TSV"

HAS_FAIL=0
HAS_BLOCKED=0
ALL_PASS=1
STEP_NUMBER=0
HANDOFF_TEMP=""
cleanup() {
  if [[ -n "$HANDOFF_TEMP" ]]; then
    rm -rf -- "$HANDOFF_TEMP"
  fi
}
trap cleanup EXIT

run_gate() {
  local name="$1"
  local blocked_code="$2"
  shift 2
  STEP_NUMBER=$((STEP_NUMBER + 1))
  local log="$LOG_DIR/$(printf '%02d' "$STEP_NUMBER")-$name.log"
  local started finished rc status
  started="$(date -u --iso-8601=seconds)"
  printf 'COMMAND=' > "$log"
  printf '%q ' "$@" >> "$log"
  printf '\nSTARTED_AT=%s\n' "$started" >> "$log"
  set +e
  "$@" 2>&1 | tee -a "$log"
  rc="${PIPESTATUS[0]}"
  set -e
  finished="$(date -u --iso-8601=seconds)"
  if [[ "$rc" -eq 0 ]]; then
    status=PASS
  elif [[ "$rc" -eq "$blocked_code" || "$rc" -eq 127 ]]; then
    status=BLOCKED
    HAS_BLOCKED=1
  else
    status=FAIL
    HAS_FAIL=1
  fi
  printf 'FINISHED_AT=%s\nRETURN_CODE=%s\nSTEP_STATUS=%s\n' \
    "$finished" "$rc" "$status" >> "$log"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$status" "$rc" "$started" "$finished" "$log" >> "$STEPS_TSV"
  [[ "$status" == PASS ]]
}

run_gate compileall 127 \
  uv run --frozen -- python -m compileall -q \
  src/loto/mlforecast tests/mlforecast || ALL_PASS=0

if [[ "$ALL_PASS" -eq 1 ]]; then
  run_gate focused-pytest 127 \
    uv run --frozen --extra dev -- pytest -q tests/mlforecast || ALL_PASS=0
fi
if [[ "$ALL_PASS" -eq 1 ]]; then
  run_gate ruff-format 127 \
    uv run --frozen --extra dev -- ruff format --check \
    src/loto/mlforecast tests/mlforecast || ALL_PASS=0
fi
if [[ "$ALL_PASS" -eq 1 ]]; then
  run_gate ruff-check 127 \
    uv run --frozen --extra dev -- ruff check \
    src/loto/mlforecast tests/mlforecast || ALL_PASS=0
fi
if [[ "$ALL_PASS" -eq 1 ]]; then
  run_gate shell-syntax 127 \
    bash -n \
    docs/mlforecast/build_handoff_bundle.sh \
    docs/mlforecast/run_runtime_certification.sh \
    docs/mlforecast/run_final_verification.sh || ALL_PASS=0
fi

if [[ "$ALL_PASS" -eq 1 ]]; then
  HANDOFF_TEMP="$(mktemp -d -t "$RUN_ID-handoff-XXXXXX")"
  run_gate strict-handoff-build 127 \
    uv run --frozen -- python -m loto.mlforecast.handoff_guard \
    --build --repo-root "$ROOT" --output-dir "$HANDOFF_TEMP" || ALL_PASS=0
fi
if [[ "$ALL_PASS" -eq 1 ]]; then
  HANDOFF_ZIP="$HANDOFF_TEMP/mlforecast-handoff-${HEAD_SHA:0:12}.zip"
  HANDOFF_SHA="$HANDOFF_ZIP.sha256"
  run_gate strict-handoff-verify 127 \
    uv run --frozen -- python -m loto.mlforecast.handoff_guard \
    --verify --zip "$HANDOFF_ZIP" --sha256 "$HANDOFF_SHA" || ALL_PASS=0
fi
if [[ "$ALL_PASS" -eq 1 ]]; then
  mkdir -p "$RUN_DIR/handoff"
  cp -a -- "$HANDOFF_ZIP" "$HANDOFF_SHA" "$RUN_DIR/handoff/"
fi

if [[ "$ALL_PASS" -eq 1 && "$SKIP_RUNTIME" != 1 ]]; then
  run_gate installed-runtime 2 \
    bash docs/mlforecast/run_runtime_certification.sh || ALL_PASS=0
fi

AFTER_HEAD="$(git rev-parse HEAD)"
AFTER_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
AFTER_COMMITTED_AT="$(git show -s --format=%cI HEAD)"
AFTER_DIRTY="$(git status --porcelain -- "${SCOPED_PATHS[@]}")"
if [[ "$AFTER_HEAD" != "$HEAD_SHA" || "$AFTER_BRANCH" != "$BRANCH" \
  || "$AFTER_COMMITTED_AT" != "$COMMITTED_AT" || -n "$AFTER_DIRTY" ]]; then
  HAS_FAIL=1
  ALL_PASS=0
  STEP_NUMBER=$((STEP_NUMBER + 1))
  LOG="$LOG_DIR/$(printf '%02d' "$STEP_NUMBER")-repository-unchanged.log"
  printf 'BEFORE=%s %s %s\nAFTER=%s %s %s\nDIRTY=%s\n' \
    "$HEAD_SHA" "$BRANCH" "$COMMITTED_AT" \
    "$AFTER_HEAD" "$AFTER_BRANCH" "$AFTER_COMMITTED_AT" "$AFTER_DIRTY" > "$LOG"
  NOW="$(date -u --iso-8601=seconds)"
  printf 'repository-unchanged\tFAIL\t1\t%s\t%s\t%s\n' \
    "$NOW" "$NOW" "$LOG" >> "$STEPS_TSV"
fi

if [[ "$HAS_FAIL" -eq 1 ]]; then
  FINAL_STATUS=FINAL_VERIFICATION_FAILED
elif [[ "$HAS_BLOCKED" -eq 1 ]]; then
  FINAL_STATUS=FINAL_VERIFICATION_BLOCKED
elif [[ "$SKIP_RUNTIME" == 1 ]]; then
  FINAL_STATUS=FINAL_VERIFICATION_PARTIAL
elif [[ "$ALL_PASS" -eq 1 ]]; then
  FINAL_STATUS=FINAL_VERIFICATION_PASSED
else
  FINAL_STATUS=FINAL_VERIFICATION_FAILED
fi

python3 - "$RUN_DIR" "$RUN_ID" "$FINAL_STATUS" "$HEAD_SHA" "$BRANCH" \
  "$COMMITTED_AT" "$SKIP_RUNTIME" "$STEPS_TSV" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

run_dir = Path(sys.argv[1])
run_id, status, commit, branch, committed_at, skip_runtime = sys.argv[2:8]
steps_path = Path(sys.argv[8])
steps = []
for line in steps_path.read_text(encoding="utf-8").splitlines():
    name, step_status, returncode, started, finished, log = line.split("\t", 5)
    steps.append({
        "name": name,
        "status": step_status,
        "returncode": int(returncode),
        "started_at": started,
        "finished_at": finished,
        "log_path": log,
    })
report = {
    "format": 1,
    "status": status,
    "run_id": run_id,
    "run_dir": str(run_dir),
    "finished_at": datetime.now(UTC).isoformat(),
    "runtime_skipped": skip_runtime == "1",
    "repository": {
        "commit": commit,
        "branch": branch,
        "committed_at": committed_at,
    },
    "environment": {
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count(),
        "thread_variables": {
            key: os.environ.get(key)
            for key in (
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    },
    "steps": steps,
}
(run_dir / "FINAL_VERIFICATION.json").write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
excluded = {"ARTIFACT_MANIFEST.json", "SHA256SUMS"}
records = []
for path in sorted(run_dir.rglob("*")):
    if not path.is_file() or path.name in excluded:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records.append({
        "path": path.relative_to(run_dir).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": digest,
    })
(run_dir / "ARTIFACT_MANIFEST.json").write_text(
    json.dumps({"format": 1, "artifacts": records}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
(run_dir / "SHA256SUMS").write_text(
    "".join(f"{item['sha256']}  {item['path']}\n" for item in records),
    encoding="utf-8",
)
PY

printf 'FINAL_STATUS=%s\nRUN_ID=%s\nRUN_DIR=%s\n' \
  "$FINAL_STATUS" "$RUN_ID" "$RUN_DIR"
[[ "$FINAL_STATUS" == FINAL_VERIFICATION_PASSED ]]
