#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_APPROVAL='APPROVE TIMER BASE 84M EXACT BYTES AND LOCK'
APPROVAL="${1:-}"
CTX="${2:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_PACKET_SHA='0d7800ae8b70274b034cc5a37893ae806b21f0bee8da5854a470ffe257491512'
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'

fail() {
  echo
  echo '============================================================'
  echo 'STOPPED SAFELY'
  echo "REASON=$1"
  echo "EXIT_CODE=${2:-1}"
  echo '============================================================'
  exit "${2:-1}"
}

[[ "$APPROVAL" == "$EXPECTED_APPROVAL" ]] || fail 'explicit approval phrase not supplied exactly' 64
[[ -f "$CTX" ]] || fail "missing context: $CTX"
# shellcheck disable=SC1090
source "$CTX"
cd "$WORKTREE" || fail "cannot enter worktree: $WORKTREE"

RUN_ID="$(basename "$EVIDENCE")"
OUT="audit/local-runs/$RUN_ID"
ENV_DIR="environments/timer-base-84m-supported-py310"
LOCK="$ENV_DIR/uv.lock"
REMOTE_REVIEW="audit/tsfm-runtime/timer-base-84m/remote-code-review.json"
DEP_REVIEW="$OUT/dependency-lock-review.json"
APPROVAL_RECORD="$OUT/HUMAN_APPROVAL.json"
PACKET="$EVIDENCE/timer-b2-human-review-packet.txt"
SNAP="$HOME/.cache/loto/timer-base-84m/snapshots/70077a71acce1b4c00d98332fcaabc694255d8e5"

printf '=== 1. Synchronize exact PR branch ===\n'
git fetch origin "$HEAD_REF" main
REMOTE_BASE="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$REMOTE_BASE" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before approval recording'
echo "PASS PR_HEAD=$REMOTE_BASE"

printf '\n=== 2. Reverify exact review packet, lock, and executable bytes ===\n'
[[ -f "$PACKET" ]] || fail "missing review packet: $PACKET"
PACKET_SHA="$(sha256sum "$PACKET" | awk '{print $1}')"
[[ "$PACKET_SHA" == "$EXPECTED_PACKET_SHA" ]] || fail "review packet SHA mismatch: $PACKET_SHA"
[[ -f "$LOCK" ]] || fail "missing isolated lock: $LOCK"
LOCK_SHA="$(sha256sum "$LOCK" | awk '{print $1}')"
[[ "$LOCK_SHA" == "$EXPECTED_LOCK_SHA" ]] || fail "isolated lock SHA mismatch: $LOCK_SHA"

cat > "$EVIDENCE/timer-approval-expected-remote-code.sha256" <<'EOF'
bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173  configuration_timer.py
a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad  modeling_timer.py
357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1  ts_generation_mixin.py
EOF
(
  cd "$SNAP"
  sha256sum -c "$EVIDENCE/timer-approval-expected-remote-code.sha256"
) || fail 'exact remote-code SHA verification failed'
echo 'PASS EXACT_APPROVAL_IDENTITIES'

printf '\n=== 3. Resolve named human reviewer ===\n'
REVIEWER="$(gh api user --jq '.login')" || fail 'cannot resolve authenticated GitHub reviewer'
[[ -n "$REVIEWER" ]] || fail 'empty GitHub reviewer identity'
REVIEWED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "REVIEWER=$REVIEWER"
echo "REVIEWED_AT=$REVIEWED_AT"

printf '\n=== 4. Persist approval bound to exact bytes ===\n'
REMOTE_REVIEW="$REMOTE_REVIEW" \
DEP_REVIEW="$DEP_REVIEW" \
APPROVAL_RECORD="$APPROVAL_RECORD" \
LOCK="$LOCK" \
PACKET="$PACKET" \
EXPECTED_PACKET_SHA="$EXPECTED_PACKET_SHA" \
EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" \
REVIEWER="$REVIEWER" \
REVIEWED_AT="$REVIEWED_AT" \
PR_HEAD="$REMOTE_BASE" \
python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

remote_path = Path(os.environ['REMOTE_REVIEW'])
dep_path = Path(os.environ['DEP_REVIEW'])
approval_path = Path(os.environ['APPROVAL_RECORD'])
lock_path = Path(os.environ['LOCK'])
packet_path = Path(os.environ['PACKET'])
reviewer = os.environ['REVIEWER']
reviewed_at = os.environ['REVIEWED_AT']
pr_head = os.environ['PR_HEAD']
expected_packet = os.environ['EXPECTED_PACKET_SHA']
expected_lock = os.environ['EXPECTED_LOCK_SHA']

expected_exec = {
    'configuration_timer.py': 'bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173',
    'modeling_timer.py': 'a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad',
    'ts_generation_mixin.py': '357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

if sha(packet_path) != expected_packet:
    raise SystemExit('review packet changed during approval recording')
if sha(lock_path) != expected_lock:
    raise SystemExit('dependency lock changed during approval recording')

remote = json.loads(remote_path.read_text(encoding='utf-8'))
if remote.get('model_revision') != '70077a71acce1b4c00d98332fcaabc694255d8e5':
    raise SystemExit('remote review model revision mismatch')
for name, digest in expected_exec.items():
    if remote.get('files', {}).get(name) != digest:
        raise SystemExit(f'remote review executable digest mismatch: {name}')
if remote.get('execution_boundary', {}).get('model_import_executed') is not False:
    raise SystemExit('remote-code import boundary is not false before approval')
if remote.get('execution_boundary', {}).get('checkpoint_load_executed') is not False:
    raise SystemExit('checkpoint-load boundary is not false before approval')

remote['review_status'] = 'HUMAN_REVIEW_APPROVED'
remote['approved'] = True
remote['trust_remote_code_allowed'] = True
remote['reviewer'] = reviewer
remote['reviewed_at_utc'] = reviewed_at
remote['review_artifact'] = {
    'kind': 'timer-b2-human-review-packet',
    'sha256': expected_packet,
}
remote.setdefault('review_notes', []).append(
    'Named human reviewer explicitly approved the exact executable bytes and exact isolated dependency lock.'
)
remote_path.write_text(json.dumps(remote, indent=2, sort_keys=True) + '\n', encoding='utf-8')

dep = json.loads(dep_path.read_text(encoding='utf-8'))
if dep.get('lock_sha256') != expected_lock:
    raise SystemExit('dependency review lock digest mismatch')
if dep.get('artifacts_without_hash'):
    raise SystemExit('dependency review contains artifacts without hashes')
if dep.get('non_registry_dependencies'):
    raise SystemExit('dependency review contains non-registry dependencies')
dep['decision'] = 'HUMAN_REVIEW_APPROVED'
dep['human_approved'] = True
dep['reviewer'] = reviewer
dep['reviewed_at_utc'] = reviewed_at
dep['review_artifact_sha256'] = expected_packet
dep_path.write_text(json.dumps(dep, indent=2, sort_keys=True) + '\n', encoding='utf-8')

approval = {
    'schema_version': 'timer-base-84m.human-approval.v1',
    'decision': 'APPROVED',
    'reviewer': reviewer,
    'reviewed_at_utc': reviewed_at,
    'pr_head_before_approval_commit': pr_head,
    'repo_id': 'thuml/timer-base-84m',
    'model_revision': '70077a71acce1b4c00d98332fcaabc694255d8e5',
    'weight_sha256': '9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d',
    'snapshot_manifest_sha256': '0cc9cd7d341e7a103f7c6bc4e3067af97dd4940576719d1bdd7ebcf3b3c54c2a',
    'executable_sha256': expected_exec,
    'dependency_lock_sha256': expected_lock,
    'review_packet_sha256': expected_packet,
    'runtime_certified': False,
    'forecast_accuracy_certified': False,
}
approval_path.write_text(json.dumps(approval, indent=2, sort_keys=True) + '\n', encoding='utf-8')

print('REMOTE_REVIEW_SHA256=' + sha(remote_path))
print('DEPENDENCY_REVIEW_SHA256=' + sha(dep_path))
print('APPROVAL_RECORD_SHA256=' + sha(approval_path))
PY

printf '\n=== 5. Stage exact approval artifacts only ===\n'
git add "$REMOTE_REVIEW" "$DEP_REVIEW" "$APPROVAL_RECORD"
STAGED="$(git diff --cached --name-only | LC_ALL=C sort)"
EXPECTED="$(printf '%s\n' "$REMOTE_REVIEW" "$DEP_REVIEW" "$APPROVAL_RECORD" | LC_ALL=C sort)"
[[ "$STAGED" == "$EXPECTED" ]] || {
  echo '--- EXPECTED ---'
  printf '%s\n' "$EXPECTED"
  echo '--- STAGED ---'
  printf '%s\n' "$STAGED"
  fail 'approval staged-scope mismatch'
}
UNSTAGED="$(git diff --name-only)"
UNTRACKED="$(git ls-files --others --exclude-standard)"
[[ -z "$UNSTAGED" ]] || {
  printf '%s\n' "$UNSTAGED"
  fail 'unexpected unstaged tracked changes after approval staging'
}
[[ -z "$UNTRACKED" ]] || {
  printf '%s\n' "$UNTRACKED"
  fail 'unexpected untracked files after approval staging'
}
echo 'PASS APPROVAL_STAGED_SCOPE'

printf '\n=== 6. Commit, race-check, and push ===\n'
git commit -m 'audit(timer): record exact-byte human approval'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
[[ "$REMOTE_NOW" == "$REMOTE_BASE" ]] || fail 'PR branch moved after approval verification; push aborted'
git merge-base --is-ancestor "$REMOTE_NOW" HEAD || fail 'approval commit is not descendant of remote PR head'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote SHA mismatch after approval push'

echo
echo '============================================================'
echo 'STATUS=PHASE_B2_B3_HUMAN_APPROVAL_PUSHED'
echo "REVIEWER=$REVIEWER"
echo "REVIEWED_AT=$REVIEWED_AT"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo "REVIEW_PACKET_SHA256=$PACKET_SHA"
echo "LOCK_SHA256=$LOCK_SHA"
echo 'REMOTE_CODE_IMPORTED=false'
echo 'CHECKPOINT_LOADED=false'
echo 'CPU_INFERENCE=false'
echo 'CUDA_INFERENCE=false'
echo '============================================================'
