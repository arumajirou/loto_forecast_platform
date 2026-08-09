#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_CONFIG_SHA='8cf274b6192f6114a0988d1e70277c69531db3611866ae7d4c6f82819c469c7e'
EXPECTED_CPU_SHA='fcdb5aa0f1c306bb1fce7613ad58a5e89601e5b1b46472ff7a74a502b272be83'
EXPECTED_CUDA_SHA='d6b54e3f2bed42d7d81f0cbef200c7bf11ed72506472061d7b6b10a825ec8817'
MATRIX_DIR='audit/local-runs/timer-formal-matrix-20260809T103953Z'
REPLAY_DIR='audit/local-runs/timer-separate-process-replay-20260809T104240Z'
VENV="$HOME/.cache/loto/timer-base-84m/venvs/$EXPECTED_LOCK_SHA"

fail() {
  echo
  echo '============================================================'
  echo 'STOPPED SAFELY'
  echo "REASON=$1"
  echo "EXIT_CODE=${2:-1}"
  echo '============================================================'
  exit "${2:-1}"
}

[[ -f "$CTX" ]] || fail "missing context: $CTX"
# shellcheck disable=SC1090
source "$CTX"
cd "$WORKTREE" || fail "cannot enter worktree: $WORKTREE"

RUN_ID="timer-repository-verification-$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="audit/local-runs/$RUN_ID"
LOCAL_OUT="$EVIDENCE/$RUN_ID"
mkdir -p "$OUT" "$LOCAL_OUT"

printf '=== 1. Synchronize exact PR head and verify clean source state ===\n'
git fetch origin "$HEAD_REF" main
SOURCE_HEAD="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$SOURCE_HEAD" ]] || fail 'local worktree did not reach remote PR head'
# OUT was created before the cleanliness check; ignore only this run directory.
DIRTY="$(git status --porcelain --untracked-files=all | grep -v "^?? $OUT/" || true)"
[[ -z "$DIRTY" ]] || { printf '%s\n' "$DIRTY"; fail 'worktree has unexpected changes before repository verification'; }
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Verify cleanup and immutable dependency boundaries ===\n'
for removed in \
  .github/workflows/timer-base-84m-lock-candidate.yml \
  .github/workflows/timer-base-84m-lock-diagnostic.yml \
  .github/workflows/timer-base-84m-lock-parser-diagnostic.yml \
  .github/workflows/timer-base-84m-snapshot-audit.yml \
  .github/workflows/timer-base-84m-snapshot-report.yml \
  scripts/maintenance/run_timer_offline_cuda_smoke.sh; do
  [[ ! -e "$removed" ]] || fail "obsolete Timer diagnostic still exists: $removed"
done
for retained in \
  scripts/maintenance/run_timer_offline_cuda_smoke_v2.sh \
  scripts/maintenance/run_timer_formal_matrix.sh \
  scripts/maintenance/timer_formal_matrix_runner.py \
  scripts/maintenance/run_timer_separate_process_replay.sh \
  scripts/maintenance/run_timer_separate_process_replay_v2.sh \
  scripts/maintenance/timer_separate_process_replay_runner.py; do
  [[ -f "$retained" ]] || fail "required final runtime evidence harness missing: $retained"
done
git diff --exit-code origin/main -- pyproject.toml uv.lock >"$OUT/root-dependency-diff.txt" 2>&1 || {
  cat "$OUT/root-dependency-diff.txt"
  fail 'root pyproject.toml or uv.lock changed'
}
LOCK='environments/timer-base-84m-supported-py310/uv.lock'
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$EXPECTED_LOCK_SHA" ]] || fail 'isolated Timer lock SHA changed'
CURRENT_CONFIG_SHA="$(PYTHONPATH="$WORKTREE/src" python3 - <<'PY'
from loto.timer_base_84m_campaign.provenance import CONFIG_SHA256
print(CONFIG_SHA256)
PY
)"
[[ "$CURRENT_CONFIG_SHA" == "$EXPECTED_CONFIG_SHA" ]] || fail "Timer config SHA mismatch: $CURRENT_CONFIG_SHA"
echo 'PASS CLEANUP_AND_DEPENDENCY_BOUNDARIES'

printf '\n=== 3. Verify final matrix and replay artifact hashes ===\n'
for evidence_dir in "$MATRIX_DIR" "$REPLAY_DIR"; do
  [[ -f "$evidence_dir/SHA256SUMS" ]] || fail "missing SHA256SUMS: $evidence_dir"
  (
    cd "$evidence_dir"
    sha256sum -c SHA256SUMS
  ) >"$OUT/$(basename "$evidence_dir")-sha256-check.txt" 2>&1 || {
    cat "$OUT/$(basename "$evidence_dir")-sha256-check.txt"
    fail "artifact hash verification failed: $evidence_dir"
  }
done
MATRIX_DIR="$MATRIX_DIR" REPLAY_DIR="$REPLAY_DIR" EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" \
EXPECTED_CPU_SHA="$EXPECTED_CPU_SHA" EXPECTED_CUDA_SHA="$EXPECTED_CUDA_SHA" python3 - <<'PY' \
  >"$OUT/evidence-semantics.txt"
import json
import os
from pathlib import Path

matrix_root = Path(os.environ['MATRIX_DIR'])
replay_root = Path(os.environ['REPLAY_DIR'])
lock_sha = os.environ['EXPECTED_LOCK_SHA']

matrix = json.loads((matrix_root / 'matrix-summary.json').read_text(encoding='utf-8'))
cpu = json.loads((matrix_root / 'cpu-summary.json').read_text(encoding='utf-8'))
cuda = json.loads((matrix_root / 'cuda-summary.json').read_text(encoding='utf-8'))
assert matrix['status'] == 'PASS'
assert matrix['total_case_count'] == 240
assert matrix['cpu_case_count'] == 120 and matrix['cuda_case_count'] == 120
assert matrix['seeds'] == [1, 7] and matrix['best_seed_selected'] is False
assert matrix['holdout_accessed'] is False and matrix['prospective_accessed'] is False
assert matrix['dependency_lock_sha256'] == lock_sha
for row in (cpu, cuda):
    assert row['status'] == 'PASS'
    assert row['cublas_workspace_config'] == ':4096:8'
    assert row['deterministic_algorithms'] is True
    assert row['cpu_fallback'] is False
    assert row['holdout_accessed'] is False and row['prospective_accessed'] is False
assert cuda['provider_pid_visible_in_nvidia_smi'] is True
assert cuda['provider_pid_released_after_exit'] is True
assert cuda['vram_released'] is True

replay = json.loads((replay_root / 'replay-summary.json').read_text(encoding='utf-8'))
assert replay['status'] == 'PASS'
assert replay['process_count'] == 4 and replay['all_provider_pids_distinct'] is True
assert replay['numerical_tolerance_used'] is False
assert replay['serialized_model_state'] is False
assert replay['holdout_accessed'] is False and replay['prospective_accessed'] is False
assert replay['dependency_lock_sha256'] == lock_sha
assert replay['cpu_replay']['prediction_sha256'] == os.environ['EXPECTED_CPU_SHA']
assert replay['cuda_replay']['prediction_sha256'] == os.environ['EXPECTED_CUDA_SHA']
for label in ('cpu-a', 'cpu-b', 'cuda-a', 'cuda-b'):
    row = json.loads((replay_root / label / 'result.json').read_text(encoding='utf-8'))
    assert row['status'] == 'PASS'
    assert row['cublas_workspace_config'] == ':4096:8'
    assert row['deterministic_algorithms'] is True
    assert row['holdout_accessed'] is False and row['prospective_accessed'] is False
for label in ('cuda-a', 'cuda-b'):
    ext = json.loads((replay_root / label / 'external-gpu-evidence.json').read_text(encoding='utf-8'))
    assert ext['provider_pid_visible_in_nvidia_smi'] is True
    assert ext['provider_pid_released_after_exit'] is True
    assert ext['vram_released'] is True
print('PASS FINAL_MATRIX_AND_REPLAY_SEMANTICS')
PY
cat "$OUT/evidence-semantics.txt"

printf '\n=== 4. Focused Ruff format/check ===\n'
command -v uv >/dev/null 2>&1 || fail 'uv is required'
mapfile -t TIMER_TESTS < <(find tests -type f -name '*timer*' -name '*.py' -print | LC_ALL=C sort)
(( ${#TIMER_TESTS[@]} > 0 )) || fail 'no Timer tests found'
RUFF_TARGETS=(
  src/loto/adapters/timer_base_84m
  src/loto/timer_base_84m_campaign
  src/loto/version.py
  scripts/maintenance/timer_formal_matrix_runner.py
  scripts/maintenance/timer_separate_process_replay_runner.py
  tests/unit/test_timer_base_84m_runtime_provider.py
)
uv run --frozen --extra dev ruff format --check "${RUFF_TARGETS[@]}" >"$OUT/ruff-format.txt" 2>&1 || {
  cat "$OUT/ruff-format.txt"
  fail 'focused ruff format failed'
}
uv run --frozen --extra dev ruff check "${RUFF_TARGETS[@]}" >"$OUT/ruff-check.txt" 2>&1 || {
  cat "$OUT/ruff-check.txt"
  fail 'focused ruff check failed'
}
echo 'PASS FOCUSED_RUFF'

printf '\n=== 5. Focused mypy ===\n'
uv run --frozen --extra dev mypy \
  src/loto/adapters/timer_base_84m \
  src/loto/timer_base_84m_campaign \
  src/loto/version.py \
  >"$OUT/mypy.txt" 2>&1 || {
    cat "$OUT/mypy.txt"
    fail 'focused mypy failed'
  }
echo 'PASS FOCUSED_MYPY'

printf '\n=== 6. Python 3.10 compatibility compile ===\n'
[[ -x "$VENV/bin/python" ]] || fail 'certified Timer Python 3.10 venv missing'
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" -m compileall -q -f \
  src/loto/adapters/timer_base_84m \
  src/loto/timer_base_84m_campaign \
  src/loto/version.py \
  scripts/maintenance/timer_formal_matrix_runner.py \
  scripts/maintenance/timer_separate_process_replay_runner.py \
  >"$OUT/compileall-py310.txt" 2>&1 || {
    cat "$OUT/compileall-py310.txt"
    fail 'Python 3.10 compile verification failed'
  }
echo 'PASS PY310_COMPILE'

printf '\n=== 7. Focused Timer regression tests ===\n'
printf '%s\n' "${TIMER_TESTS[@]}" >"$OUT/timer-tests-list.txt"
uv run --frozen --extra dev pytest "${TIMER_TESTS[@]}" >"$OUT/pytest-timer.txt" 2>&1 || {
  cat "$OUT/pytest-timer.txt"
  fail 'focused Timer pytest failed'
}
cat "$OUT/pytest-timer.txt"
echo 'PASS FOCUSED_TIMER_TESTS'

printf '\n=== 8. Diff hygiene and changed-file size scan ===\n'
git diff --check origin/main...HEAD >"$OUT/git-diff-check.txt" 2>&1 || {
  cat "$OUT/git-diff-check.txt"
  fail 'git diff --check failed'
}
python3 - <<'PY' >"$OUT/changed-file-size-scan.txt"
from pathlib import Path
import subprocess

limit = 5 * 1024 * 1024
names = subprocess.check_output(
    ['git', 'diff', '--name-only', '--diff-filter=ACMR', 'origin/main...HEAD'],
    text=True,
).splitlines()
oversized = []
for name in names:
    path = Path(name)
    if path.is_file():
        size = path.stat().st_size
        if size > limit:
            oversized.append((name, size))
if oversized:
    raise SystemExit('changed files exceed 5 MiB: ' + repr(oversized))
print(f'PASS changed_file_count={len(names)} max_allowed_bytes={limit}')
PY
echo 'PASS DIFF_HYGIENE'

printf '\n=== 9. Write verification summary and SHA256SUMS ===\n'
SOURCE_HEAD="$SOURCE_HEAD" RUN_ID="$RUN_ID" python3 - <<'PY' >"$OUT/VERIFICATION_RESULT.json"
import json
import os
print(json.dumps({
    'schema_version': 'timer-base-84m.repository-verification.v1',
    'status': 'PASS',
    'run_id': os.environ['RUN_ID'],
    'source_head_sha': os.environ['SOURCE_HEAD'],
    'focused_ruff': 'PASS',
    'focused_mypy': 'PASS',
    'python_3_10_compile': 'PASS',
    'focused_timer_tests': 'PASS',
    'final_matrix_artifact_hashes': 'PASS',
    'final_replay_artifact_hashes': 'PASS',
    'final_matrix_replay_semantics': 'PASS',
    'cleanup_verified': True,
    'root_dependency_files_unchanged': True,
    'holdout_accessed': False,
    'prospective_accessed': False,
    'full_pytest_executed': False,
}, indent=2, sort_keys=True))
PY
(
  cd "$OUT"
  find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > SHA256SUMS
  sha256sum -c SHA256SUMS
)
cp -a "$OUT/." "$LOCAL_OUT/"

printf '\n=== 10. Race-check, strict stage scope, commit, and push evidence ===\n'
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved during repository verification; evidence retained locally, push aborted'
git add "$OUT"
STAGED="$(git diff --cached --name-only)"
[[ -n "$STAGED" ]] || fail 'no repository verification evidence staged'
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in "$OUT"/*) ;; *) fail "unexpected staged path: $path" ;; esac
done <<< "$STAGED"
git commit -m 'evidence(timer): add final repository verification'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved after verification commit; push aborted'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote head mismatch after verification push'

printf '\n============================================================\n'
echo 'STATUS=TIMER_REPOSITORY_VERIFICATION_EVIDENCE_PUSHED'
echo "RUN_ID=$RUN_ID"
echo "SOURCE_HEAD=$SOURCE_HEAD"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo 'CLEANUP=PASS'
echo 'RUFF=PASS'
echo 'MYPY=PASS'
echo 'PY310_COMPILE=PASS'
echo 'TIMER_TESTS=PASS'
echo 'FINAL_MATRIX_SHA256=PASS'
echo 'FINAL_REPLAY_SHA256=PASS'
echo 'HOLDOUT_ACCESSED=false'
echo 'PROSPECTIVE_ACCESSED=false'
echo 'FULL_PYTEST_EXECUTED=false'
echo 'NEXT=FULL_PYTEST_ONCE'
echo '============================================================'
