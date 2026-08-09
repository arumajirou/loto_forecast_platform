#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_REMOTE_REVIEW_SHA='6055342d1faf77c0e831146cf1e8c670c660c640e0bdaba767e20399153d83b0'
EXPECTED_DEP_REVIEW_SHA='baca6625226658146b8399648d920ff57c62d752fe10cf000ad3205d395d213f'
EXPECTED_APPROVAL_RECORD_SHA='b04900186097b58117d36832da6512cfd46a9a1786befac72e0e7c1f3b321834'
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_REVIEWER='arumajirou'
EXPECTED_REVIEWED_AT='2026-08-09T09:10:50Z'

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

RUN_ID="$(basename "$EVIDENCE")"
OUT="audit/local-runs/$RUN_ID"
REMOTE_REVIEW="audit/tsfm-runtime/timer-base-84m/remote-code-review.json"
DEP_REVIEW="$OUT/dependency-lock-review.json"
APPROVAL_RECORD="$OUT/HUMAN_APPROVAL.json"
LOCK="environments/timer-base-84m-supported-py310/uv.lock"

printf '=== 1. Synchronize support fix without touching approval artifacts ===\n'
git fetch origin "$HEAD_REF" main
REMOTE_BASE="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$REMOTE_BASE" ]] || fail 'local worktree did not reach remote PR head'
echo "PASS PR_HEAD=$REMOTE_BASE"

printf '\n=== 2. Permit only the known partial approval artifacts ===\n'
STATUS="$(git status --porcelain --untracked-files=all)"
if [[ -n "$STATUS" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    path="${line:3}"
    case "$path" in
      "$REMOTE_REVIEW"|"$DEP_REVIEW"|"$APPROVAL_RECORD") ;;
      *)
        printf '%s\n' "$STATUS"
        fail "unexpected local change while resuming approval push: $path"
        ;;
    esac
  done <<< "$STATUS"
fi
echo 'PASS RESUMABLE_WORKTREE_SCOPE'

printf '\n=== 3. Verify exact previously generated approval bytes ===\n'
for f in "$REMOTE_REVIEW" "$DEP_REVIEW" "$APPROVAL_RECORD" "$LOCK"; do
  [[ -f "$f" ]] || fail "missing expected file: $f"
done
REMOTE_SHA="$(sha256sum "$REMOTE_REVIEW" | awk '{print $1}')"
DEP_SHA="$(sha256sum "$DEP_REVIEW" | awk '{print $1}')"
APPROVAL_SHA="$(sha256sum "$APPROVAL_RECORD" | awk '{print $1}')"
LOCK_SHA="$(sha256sum "$LOCK" | awk '{print $1}')"
[[ "$REMOTE_SHA" == "$EXPECTED_REMOTE_REVIEW_SHA" ]] || fail "remote review SHA mismatch: $REMOTE_SHA"
[[ "$DEP_SHA" == "$EXPECTED_DEP_REVIEW_SHA" ]] || fail "dependency review SHA mismatch: $DEP_SHA"
[[ "$APPROVAL_SHA" == "$EXPECTED_APPROVAL_RECORD_SHA" ]] || fail "approval record SHA mismatch: $APPROVAL_SHA"
[[ "$LOCK_SHA" == "$EXPECTED_LOCK_SHA" ]] || fail "lock SHA mismatch: $LOCK_SHA"

echo "PASS REMOTE_REVIEW_SHA256=$REMOTE_SHA"
echo "PASS DEPENDENCY_REVIEW_SHA256=$DEP_SHA"
echo "PASS APPROVAL_RECORD_SHA256=$APPROVAL_SHA"
echo "PASS LOCK_SHA256=$LOCK_SHA"

REMOTE_REVIEW="$REMOTE_REVIEW" DEP_REVIEW="$DEP_REVIEW" APPROVAL_RECORD="$APPROVAL_RECORD" \
EXPECTED_REVIEWER="$EXPECTED_REVIEWER" EXPECTED_REVIEWED_AT="$EXPECTED_REVIEWED_AT" \
EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" python3 - <<'PY'
import json
import os
from pathlib import Path

remote = json.loads(Path(os.environ['REMOTE_REVIEW']).read_text(encoding='utf-8'))
dep = json.loads(Path(os.environ['DEP_REVIEW']).read_text(encoding='utf-8'))
approval = json.loads(Path(os.environ['APPROVAL_RECORD']).read_text(encoding='utf-8'))
reviewer = os.environ['EXPECTED_REVIEWER']
reviewed_at = os.environ['EXPECTED_REVIEWED_AT']
lock_sha = os.environ['EXPECTED_LOCK_SHA']

if remote.get('review_status') != 'HUMAN_REVIEW_APPROVED' or remote.get('approved') is not True:
    raise SystemExit('remote review is not approved')
if remote.get('trust_remote_code_allowed') is not True:
    raise SystemExit('trust_remote_code_allowed is not true')
if remote.get('reviewer') != reviewer or remote.get('reviewed_at_utc') != reviewed_at:
    raise SystemExit('remote review reviewer/time mismatch')
if dep.get('decision') != 'HUMAN_REVIEW_APPROVED' or dep.get('human_approved') is not True:
    raise SystemExit('dependency review is not human-approved')
if dep.get('reviewer') != reviewer or dep.get('reviewed_at_utc') != reviewed_at:
    raise SystemExit('dependency review reviewer/time mismatch')
if dep.get('lock_sha256') != lock_sha:
    raise SystemExit('dependency review lock SHA mismatch')
if approval.get('decision') != 'APPROVED':
    raise SystemExit('approval record decision mismatch')
if approval.get('reviewer') != reviewer or approval.get('reviewed_at_utc') != reviewed_at:
    raise SystemExit('approval record reviewer/time mismatch')
if approval.get('dependency_lock_sha256') != lock_sha:
    raise SystemExit('approval record lock SHA mismatch')
if approval.get('runtime_certified') is not False:
    raise SystemExit('runtime_certified must still be false')
print('PASS HUMAN_APPROVAL_SEMANTICS')
PY

printf '\n=== 4. Stage exact approval artifacts only ===\n'
git add "$REMOTE_REVIEW" "$DEP_REVIEW" "$APPROVAL_RECORD"
STAGED="$(git diff --cached --name-only | LC_ALL=C sort)"
EXPECTED="$(printf '%s\n' "$REMOTE_REVIEW" "$DEP_REVIEW" "$APPROVAL_RECORD" | LC_ALL=C sort)"
[[ "$STAGED" == "$EXPECTED" ]] || {
  echo '--- EXPECTED ---'; printf '%s\n' "$EXPECTED"
  echo '--- STAGED ---'; printf '%s\n' "$STAGED"
  fail 'approval staged-scope mismatch'
}
[[ -z "$(git diff --name-only)" ]] || fail 'unexpected unstaged tracked changes after staging'
[[ -z "$(git ls-files --others --exclude-standard)" ]] || fail 'unexpected untracked files after staging'
echo 'PASS APPROVAL_STAGED_SCOPE'

printf '\n=== 5. Commit, race-check, and push ===\n'
git commit -m 'audit(timer): record exact-byte human approval'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
[[ "$REMOTE_NOW" == "$REMOTE_BASE" ]] || fail 'PR branch moved after resume verification; push aborted'
git merge-base --is-ancestor "$REMOTE_NOW" HEAD || fail 'approval commit is not descendant of remote PR head'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote SHA mismatch after approval push'

echo
echo '============================================================'
echo 'STATUS=PHASE_B2_B3_HUMAN_APPROVAL_PUSHED'
echo "REVIEWER=$EXPECTED_REVIEWER"
echo "REVIEWED_AT=$EXPECTED_REVIEWED_AT"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo "REMOTE_REVIEW_SHA256=$REMOTE_SHA"
echo "DEPENDENCY_REVIEW_SHA256=$DEP_SHA"
echo "APPROVAL_RECORD_SHA256=$APPROVAL_SHA"
echo "LOCK_SHA256=$LOCK_SHA"
echo 'REMOTE_CODE_IMPORTED=false'
echo 'CHECKPOINT_LOADED=false'
echo 'CPU_INFERENCE=false'
echo 'CUDA_INFERENCE=false'
echo '============================================================'
