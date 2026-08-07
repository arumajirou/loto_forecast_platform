#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-/mnt/e/env/ts/loto_forecast_platform}"
DEFAULT_SNAPSHOT="/mnt/e/env/huggingface/hub/models--thuml--sundial-base-128m/snapshots"
DEFAULT_SNAPSHOT="$DEFAULT_SNAPSHOT/3212e42564493f520593e5414af4367fc4b49226"
SNAPSHOT="${2:-$DEFAULT_SNAPSHOT}"
EXPECTED_COMMIT="${3:-}"
EXPECTED_BRANCH="${EXPECTED_BRANCH:-feat/sundial-probabilistic-provider-v2}"
CASE_TIMEOUT="${CASE_TIMEOUT:-1800}"
PAUSE_ON_EXIT="${PAUSE_ON_EXIT:-1}"
export UV_FROZEN=1

cd "$ROOT" || exit 1

if [[ -z "$EXPECTED_COMMIT" ]]; then
  printf 'BLOCKED: expected commit is required\n' >&2
  exit 20
fi

CURRENT_COMMIT="$(git rev-parse HEAD)"
CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
  printf 'BLOCKED: commit mismatch\nEXPECTED=%s\nACTUAL=%s\n' \
    "$EXPECTED_COMMIT" "$CURRENT_COMMIT" >&2
  exit 21
fi
if [[ "$CURRENT_BRANCH" != "$EXPECTED_BRANCH" ]]; then
  printf 'BLOCKED: branch mismatch\nEXPECTED=%s\nACTUAL=%s\n' \
    "$EXPECTED_BRANCH" "$CURRENT_BRANCH" >&2
  exit 22
fi
if [[ -n "$(git status --porcelain=v1)" ]]; then
  printf 'BLOCKED: worktree is not clean\n' >&2
  git status --short --branch >&2
  exit 23
fi

test -d "$SNAPSHOT"
test "$(basename "$SNAPSHOT")" = \
  "3212e42564493f520593e5414af4367fc4b49226"
command -v uv >/dev/null
command -v nvidia-smi >/dev/null

GATE_ID="sundial-v2-final-gate-$(date +%Y%m%d-%H%M%S)"
GATE_DIR="artifacts/sundial-provider-v2-final-gate/$GATE_ID"
mkdir -p "$GATE_DIR"
CONSOLE_LOG="$GATE_DIR/console.log"
STATUS_FILE="$GATE_DIR/status.txt"
STARTED_AT="$(date --iso-8601=seconds)"

finish() {
  rc=$?
  {
    printf 'SUNDIAL_PROVIDER_V2_FINAL_GATE=%s\n' \
      "$([[ "$rc" -eq 0 ]] && printf PASS || printf FAIL)"
    printf 'EXIT_CODE=%s\n' "$rc"
    printf 'GATE_DIR=%s\n' "$GATE_DIR"
    printf 'EXPECTED_COMMIT=%s\n' "$EXPECTED_COMMIT"
    printf 'EXPECTED_BRANCH=%s\n' "$EXPECTED_BRANCH"
    printf 'STARTED_AT=%s\n' "$STARTED_AT"
    printf 'FINISHED_AT=%s\n' "$(date --iso-8601=seconds)"
  } | tee "$STATUS_FILE"
  if [[ "$PAUSE_ON_EXIT" == "1" && -t 0 ]]; then
    printf '\nEnterキーで終了します...'
    read -r _ || true
  fi
  exit "$rc"
}
trap finish EXIT

run_logged() {
  local name="$1"
  shift
  printf '\n=== %s ===\n' "$name" | tee -a "$CONSOLE_LOG"
  "$@" 2>&1 | tee "$GATE_DIR/${name}.log" | tee -a "$CONSOLE_LOG"
}

PYTHON_FILES=(
  scripts/run_sundial_provider.py
  scripts/certify_sundial_provider_v2.py
  scripts/verify_sundial_provider_v2_semantics.py
  scripts/verify_sundial_provider_v2_evidence.py
  src/loto/models/providers/sundial.py
  tests/test_sundial_probabilistic_provider_v2.py
  tests/test_sundial_provider_v2_certification.py
  tests/test_sundial_provider_v2_semantic_verifier.py
  tests/test_sundial_provider_v2_evidence_verifier.py
  tests/test_sundial_provider_v2_final_gate.py
  tests/test_sundial_provider_v2_remaining_hardening.py
)
FOCUSED_TESTS=(
  tests/test_sundial_probabilistic_provider_v2.py
  tests/test_sundial_provider_v2_certification.py
  tests/test_sundial_provider_v2_semantic_verifier.py
  tests/test_sundial_provider_v2_evidence_verifier.py
  tests/test_sundial_provider_v2_final_gate.py
  tests/test_sundial_provider_v2_remaining_hardening.py
)

{
  printf 'SUNDIAL_PROVIDER_V2_FINAL_GATE_START\n'
  printf 'ROOT=%s\n' "$ROOT"
  printf 'SNAPSHOT=%s\n' "$SNAPSHOT"
  printf 'EXPECTED_COMMIT=%s\n' "$EXPECTED_COMMIT"
  printf 'EXPECTED_BRANCH=%s\n' "$EXPECTED_BRANCH"
  printf 'CASE_TIMEOUT=%s\n' "$CASE_TIMEOUT"
  printf 'UV_FROZEN=%s\n' "$UV_FROZEN"
} | tee "$CONSOLE_LOG"

run_logged ruff \
  uv run --frozen --extra dev ruff check "${PYTHON_FILES[@]}"
run_logged mypy \
  uv run --frozen --extra dev mypy \
  scripts/run_sundial_provider.py \
  scripts/certify_sundial_provider_v2.py \
  scripts/verify_sundial_provider_v2_semantics.py \
  scripts/verify_sundial_provider_v2_evidence.py \
  src/loto/models/providers/sundial.py
run_logged focused-pytest \
  uv run --frozen --extra dev pytest "${FOCUSED_TESTS[@]}"

run_logged semantic-snapshot-preflight \
  uv run --frozen --extra dev python \
  scripts/verify_sundial_provider_v2_semantics.py \
  --repo-root "$ROOT" \
  --snapshot "$SNAPSHOT" \
  --snapshot-only

run_logged certification \
  uv run --frozen --extra dev python \
  scripts/certify_sundial_provider_v2.py \
  --repo-root "$ROOT" \
  --snapshot "$SNAPSHOT" \
  --sample-counts 1,3,20,50,100 \
  --replay-samples 20 \
  --seed 42 \
  --case-timeout "$CASE_TIMEOUT"

RUN_DIR="$(cat artifacts/sundial-provider-v2/LATEST)"
test -d "$RUN_DIR"
grep -Fx 'SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS' "$RUN_DIR/status.txt"
RUN_ID="$(basename "$RUN_DIR")"
SEMANTIC_REPORT="artifacts/sundial-provider-v2-semantic-verification/$RUN_ID.json"

run_logged semantic-output-verification \
  uv run --frozen --extra dev python \
  scripts/verify_sundial_provider_v2_semantics.py \
  --repo-root "$ROOT" \
  --snapshot "$SNAPSHOT" \
  --run-dir "$RUN_DIR"

test -f "$SEMANTIC_REPORT"

run_logged evidence-verification \
  uv run --frozen --extra dev python \
  scripts/verify_sundial_provider_v2_evidence.py \
  --run-dir "$RUN_DIR" \
  --repo-root "$ROOT" \
  --expected-commit "$EXPECTED_COMMIT" \
  --expected-branch "$EXPECTED_BRANCH" \
  --semantic-report "$SEMANTIC_REPORT" \
  --archive

VERIFICATION_DIR="artifacts/sundial-provider-v2-verified/$RUN_ID"
ARCHIVE="artifacts/sundial-provider-v2-verified/${RUN_ID}-evidence.zip"
test -f "$VERIFICATION_DIR/VERIFICATION_REPORT.json"
test -f "$VERIFICATION_DIR/PR_COMMENT.md"
test -f "$ARCHIVE"
test -f "$ARCHIVE.sha256"

run_logged archive-content-check \
  uv run --frozen --extra dev python -c \
  'import sys, zipfile; p=sys.argv[2]; z=zipfile.ZipFile(sys.argv[1]); assert f"semantic/{p}" in z.namelist()' \
  "$ARCHIVE" "$(basename "$SEMANTIC_REPORT")"

run_logged full-pytest uv run --frozen --extra dev pytest

{
  printf 'RUN_DIR=%s\n' "$RUN_DIR"
  printf 'SEMANTIC_REPORT=%s\n' "$SEMANTIC_REPORT"
  printf 'VERIFICATION_DIR=%s\n' "$VERIFICATION_DIR"
  printf 'ARCHIVE=%s\n' "$ARCHIVE"
  printf 'ARCHIVE_SHA256_FILE=%s\n' "$ARCHIVE.sha256"
} | tee -a "$CONSOLE_LOG"
