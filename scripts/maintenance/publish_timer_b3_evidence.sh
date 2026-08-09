#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"

fail() {
  echo
  echo "============================================================"
  echo "STOPPED SAFELY"
  echo "REASON=$1"
  echo "EXIT_CODE=${2:-1}"
  echo "============================================================"
  exit "${2:-1}"
}

[[ -f "$CTX" ]] || fail "missing context: $CTX"
# shellcheck disable=SC1090
source "$CTX"

cd "$WORKTREE" || fail "cannot enter worktree"

RUN_ID="$(basename "$EVIDENCE")"
OUT="audit/local-runs/$RUN_ID"
ENV_DIR="environments/timer-base-84m-supported-py310"
LOCK="$ENV_DIR/uv.lock"
EXPECTED_LOCK_SHA="5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0"

printf '=== 1. Synchronize exact PR branch ===\n'
git fetch origin "$HEAD_REF" main
REMOTE_BASE="$(git rev-parse "origin/$HEAD_REF")"
LOCAL_BEFORE="$(git rev-parse HEAD)"
printf 'LOCAL_BEFORE=%s\nREMOTE_BASE=%s\n' "$LOCAL_BEFORE" "$REMOTE_BASE"

git merge --ff-only "origin/$HEAD_REF" || fail "local worktree cannot fast-forward to PR branch"
LOCAL_SYNCED="$(git rev-parse HEAD)"
[[ "$LOCAL_SYNCED" == "$REMOTE_BASE" ]] || fail "local worktree did not reach remote PR head"

echo "PASS FAST_FORWARD=$LOCAL_SYNCED"

printf '\n=== 2. Verify generated evidence ===\n'
for f in \
  "$LOCK" \
  "$OUT/EXECUTION_RESULT.json" \
  "$OUT/active-lock-analysis.json" \
  "$OUT/dependency-license-review.json" \
  "$OUT/dependency-lock-review.json" \
  "$OUT/gpu-inventory.txt" \
  "$OUT/uv-pip-check.txt" \
  "$OUT/SHA256SUMS"
do
  [[ -f "$f" ]] || fail "missing expected file: $f"
done

LOCK_SHA="$(sha256sum "$LOCK" | awk '{print $1}')"
[[ "$LOCK_SHA" == "$EXPECTED_LOCK_SHA" ]] || fail "unexpected Timer lock SHA: $LOCK_SHA"

if git check-ignore -q "$OUT/EXECUTION_RESULT.json"; then
  fail "audit/local-runs is still ignored"
fi

(
  cd "$OUT"
  sha256sum -c SHA256SUMS
) || fail "SHA256SUMS verification failed"

echo "PASS EVIDENCE_HASHES"

printf '\n=== 3. Verify no unrelated worktree changes ===\n'
ALLOWED_REGEX="^(\\?\\? |A  |M  )(${ENV_DIR}/uv\\.lock|${OUT}/(EXECUTION_RESULT\\.json|SHA256SUMS|active-lock-analysis\\.json|dependency-license-review\\.json|dependency-lock-review\\.json|gpu-inventory\\.txt|uv-pip-check\\.txt))$"
BAD_STATUS="$(git status --porcelain | grep -Ev "$ALLOWED_REGEX" || true)"
if [[ -n "$BAD_STATUS" ]]; then
  printf '%s\n' "$BAD_STATUS"
  fail "unexpected local worktree changes detected"
fi

echo "PASS WORKTREE_SCOPE"

printf '\n=== 4. Stage strict allowlist ===\n'
git add \
  "$LOCK" \
  "$OUT/EXECUTION_RESULT.json" \
  "$OUT/active-lock-analysis.json" \
  "$OUT/dependency-license-review.json" \
  "$OUT/dependency-lock-review.json" \
  "$OUT/gpu-inventory.txt" \
  "$OUT/uv-pip-check.txt" \
  "$OUT/SHA256SUMS"

STAGED="$(git diff --cached --name-only)"
printf '%s\n' "$STAGED"
COUNT="$(printf '%s\n' "$STAGED" | sed '/^$/d' | wc -l)"
[[ "$COUNT" == "8" ]] || fail "expected 8 staged files, got $COUNT"

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    "$LOCK"|"$OUT/EXECUTION_RESULT.json"|"$OUT/active-lock-analysis.json"|"$OUT/dependency-license-review.json"|"$OUT/dependency-lock-review.json"|"$OUT/gpu-inventory.txt"|"$OUT/uv-pip-check.txt"|"$OUT/SHA256SUMS") ;;
    *) fail "unexpected staged path: $path" ;;
  esac
done <<< "$STAGED"

echo "PASS STAGED_SCOPE"

printf '\n=== 5. Protect root dependency files ===\n'
git diff --exit-code "origin/main" -- pyproject.toml uv.lock || fail "root dependency files changed"
echo "PASS ROOT_DEPENDENCIES_UNCHANGED"

printf '\n=== 6. Commit ===\n'
git commit -m "evidence(timer): add local Phase B3 dependency verification"
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
echo "LOCAL_NEW_HEAD=$LOCAL_NEW_HEAD"

printf '\n=== 7. Race check and fast-forward push ===\n'
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
printf 'REMOTE_NOW=%s\nREMOTE_BASE=%s\n' "$REMOTE_NOW" "$REMOTE_BASE"
[[ "$REMOTE_NOW" == "$REMOTE_BASE" ]] || fail "PR branch moved after local synchronization"
git merge-base --is-ancestor "$REMOTE_NOW" HEAD || fail "local commit is not a descendant of remote PR head"
git push origin "HEAD:$HEAD_REF"

git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail "remote SHA mismatch after push"

echo
echo "============================================================"
echo "STATUS=PHASE_B3_EVIDENCE_PUSHED"
echo "PR=$PR"
echo "BRANCH=$HEAD_REF"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo "LOCK_SHA256=$LOCK_SHA"
echo "EVIDENCE_PATH=$OUT"
echo "REMOTE_CODE_APPROVAL=PENDING"
echo "MODEL_LOAD=NOT_EXECUTED"
echo "CPU_INFERENCE=NOT_EXECUTED"
echo "CUDA_INFERENCE=NOT_EXECUTED"
echo "============================================================"
