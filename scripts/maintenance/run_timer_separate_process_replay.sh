#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_PACKET_SHA='0d7800ae8b70274b034cc5a37893ae806b21f0bee8da5854a470ffe257491512'
EXPECTED_SNAPSHOT_MANIFEST_SHA='0cc9cd7d341e7a103f7c6bc4e3067af97dd4940576719d1bdd7ebcf3b3c54c2a'
REV='70077a71acce1b4c00d98332fcaabc694255d8e5'
GPU_INDEX='0'
VRAM_MIN_FREE_MIB='900'
VRAM_RELEASE_TOLERANCE_MIB='256'

fail() {
  echo
  echo '============================================================'
  echo 'STOPPED SAFELY'
  echo "REASON=$1"
  echo "EXIT_CODE=${2:-1}"
  echo '============================================================'
  exit "${2:-1}"
}

proc_is_running_non_zombie() {
  local pid="$1"
  [[ -r "/proc/$pid/stat" ]] || return 1
  local state
  state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)"
  [[ -n "$state" && "$state" != 'Z' ]]
}

[[ -f "$CTX" ]] || fail "missing context: $CTX"
# shellcheck disable=SC1090
source "$CTX"
cd "$WORKTREE" || fail "cannot enter worktree: $WORKTREE"

BASE_RUN_ID="$(basename "$EVIDENCE")"
APPROVAL_RECORD="audit/local-runs/$BASE_RUN_ID/HUMAN_APPROVAL.json"
REMOTE_REVIEW="audit/tsfm-runtime/timer-base-84m/remote-code-review.json"
DEP_REVIEW="audit/local-runs/$BASE_RUN_ID/dependency-lock-review.json"
LOCK="environments/timer-base-84m-supported-py310/uv.lock"
SNAP="$HOME/.cache/loto/timer-base-84m/snapshots/$REV"
VENV="$HOME/.cache/loto/timer-base-84m/venvs/$EXPECTED_LOCK_SHA"
FORMAL_RUNNER="scripts/maintenance/timer_formal_matrix_runner.py"
REPLAY_RUNNER="scripts/maintenance/timer_separate_process_replay_runner.py"
SELF="scripts/maintenance/run_timer_separate_process_replay.sh"
RUN_ID="timer-separate-process-replay-$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="audit/local-runs/$RUN_ID"
LOCAL_OUT="$EVIDENCE/$RUN_ID"
mkdir -p "$LOCAL_OUT"

printf '=== 1. Synchronize exact PR head and verify clean worktree ===\n'
git fetch origin "$HEAD_REF" main
SOURCE_HEAD="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$SOURCE_HEAD" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before replay'
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Reverify approval, lock, runner, and exact snapshot ===\n'
for f in "$APPROVAL_RECORD" "$REMOTE_REVIEW" "$DEP_REVIEW" "$LOCK" "$FORMAL_RUNNER" "$REPLAY_RUNNER" "$SELF"; do
  [[ -f "$f" ]] || fail "missing required artifact: $f"
done
[[ -x "$VENV/bin/python" ]] || fail 'isolated Timer Python environment missing'
[[ -d "$SNAP" ]] || fail 'pinned local snapshot missing'
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$EXPECTED_LOCK_SHA" ]] || fail 'isolated lock SHA changed'

APPROVAL_RECORD="$APPROVAL_RECORD" REMOTE_REVIEW="$REMOTE_REVIEW" DEP_REVIEW="$DEP_REVIEW" \
EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" EXPECTED_PACKET_SHA="$EXPECTED_PACKET_SHA" python3 - <<'PY'
import json
import os
from pathlib import Path
approval = json.loads(Path(os.environ['APPROVAL_RECORD']).read_text(encoding='utf-8'))
remote = json.loads(Path(os.environ['REMOTE_REVIEW']).read_text(encoding='utf-8'))
dep = json.loads(Path(os.environ['DEP_REVIEW']).read_text(encoding='utf-8'))
if approval.get('decision') != 'APPROVED':
    raise SystemExit('human approval record is not APPROVED')
if approval.get('dependency_lock_sha256') != os.environ['EXPECTED_LOCK_SHA']:
    raise SystemExit('approval lock SHA mismatch')
if approval.get('review_packet_sha256') != os.environ['EXPECTED_PACKET_SHA']:
    raise SystemExit('approval packet SHA mismatch')
if remote.get('approved') is not True or remote.get('trust_remote_code_allowed') is not True:
    raise SystemExit('remote-code review is not approved')
if dep.get('human_approved') is not True or dep.get('lock_sha256') != os.environ['EXPECTED_LOCK_SHA']:
    raise SystemExit('dependency lock is not human-approved')
print('PASS HUMAN_APPROVAL_GATE reviewer=' + str(approval.get('reviewer')))
PY

cat > "$LOCAL_OUT/snapshot.sha256" <<'EOF'
11ad7efa24975ee4b0c3c3a38ed18737f0658a5f75a0a96787b576a78a023361  .gitattributes
da6dcfdebb53e79e97e159ca605942b7c8c580d4c816c60016349d5c5b0ed9bb  README.md
8cf274b6192f6114a0988d1e70277c69531db3611866ae7d4c6f82819c469c7e  config.json
bec2d7ed868b57d7046f097cad166d8e935920aa082cc6e9bb2cc53b9b626173  configuration_timer.py
f6f95f062b96cc8c5d0954c6540beff706aa6d0982b5474925c6639bc3b5def9  generation_config.json
9c3d18f12ffe1ea7d4fa70eb3304b26e3841164a6a265fbae4f7a05cd213aa3d  model.safetensors
a625da46370e044609f1cd601eb2899aaf8a8e2dd5966bcfadc9d7f89a5092ad  modeling_timer.py
357d4aa6fd24f107bef5665f82fe2c7df278f4ff151c4493dbaa9f43655b55a1  ts_generation_mixin.py
EOF
(
  cd "$SNAP"
  sha256sum -c "$LOCAL_OUT/snapshot.sha256"
) | tee "$LOCAL_OUT/snapshot-verify.txt"
echo 'PASS SNAPSHOT_RECHECK'

printf '\n=== 3. Compile replay code and bind code identities ===\n'
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" -m py_compile "$FORMAL_RUNNER" "$REPLAY_RUNNER" || fail 'replay Python syntax check failed'
FORMAL_RUNNER_SHA="$(sha256sum "$FORMAL_RUNNER" | awk '{print $1}')"
REPLAY_RUNNER_SHA="$(sha256sum "$REPLAY_RUNNER" | awk '{print $1}')"
SHELL_SHA="$(sha256sum "$SELF" | awk '{print $1}')"
echo "FORMAL_RUNNER_SHA256=$FORMAL_RUNNER_SHA"
echo "REPLAY_RUNNER_SHA256=$REPLAY_RUNNER_SHA"
echo "SHELL_SHA256=$SHELL_SHA"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONHASHSEED=1
export HF_HOME="$HOME/.cache/loto/timer-base-84m/hf-offline"
mkdir -p "$HF_HOME"

run_cpu() {
  local label="$1"
  local dir="$LOCAL_OUT/$label"
  mkdir -p "$dir"
  local started ended rc
  started="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  set +e
  CUDA_VISIBLE_DEVICES='' PYTHONPATH="$WORKTREE/src:$WORKTREE/scripts/maintenance" "$VENV/bin/python" "$REPLAY_RUNNER" \
    --device cpu --snapshot "$SNAP" --out-dir "$dir" --source-head "$SOURCE_HEAD" \
    --lock-sha256 "$EXPECTED_LOCK_SHA" --snapshot-manifest-sha256 "$EXPECTED_SNAPSHOT_MANIFEST_SHA" \
    --formal-runner-sha256 "$FORMAL_RUNNER_SHA" --replay-runner-sha256 "$REPLAY_RUNNER_SHA" \
    --shell-sha256 "$SHELL_SHA" >"$dir/stdout.txt" 2>"$dir/stderr.txt"
  rc=$?
  set -e
  ended="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '%s\n' "$rc" > "$dir/exitcode.txt"
  printf '%s\n' "$started" > "$dir/started_at_utc.txt"
  printf '%s\n' "$ended" > "$dir/ended_at_utc.txt"
  [[ "$rc" == '0' ]] || { tail -n 120 "$dir/stderr.txt" || true; fail "$label failed rc=$rc" "$rc"; }
  [[ -f "$dir/result.json" ]] || fail "$label result.json missing"
  echo "PASS $label"
}

printf '\n=== 4. CPU replay: two independent processes ===\n'
run_cpu cpu-a
run_cpu cpu-b

command -v nvidia-smi >/dev/null 2>&1 || fail 'nvidia-smi is not available'
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit('torch.cuda.is_available() is false')
print('PASS TORCH_CUDA_AVAILABLE')
print('CUDA_DEVICE_NAME=' + torch.cuda.get_device_name(0))
PY
GPU_UUID="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=uuid --format=csv,noheader | head -n1 | tr -d '[:space:]')"
echo "GPU_UUID=$GPU_UUID"

run_cuda() {
  local label="$1"
  local dir="$LOCAL_OUT/$label"
  mkdir -p "$dir"
  local before free_before after delta peak pid rc started ended visible snapshot match match_uuid match_mem
  before="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
  free_before="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.free --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
  [[ "$before" =~ ^[0-9]+$ && "$free_before" =~ ^[0-9]+$ ]] || fail "$label invalid VRAM preflight"
  (( free_before >= VRAM_MIN_FREE_MIB )) || fail "$label insufficient free VRAM: ${free_before} MiB"
  nvidia-smi -i "$GPU_INDEX" --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version --format=csv,noheader,nounits > "$dir/gpu-before.csv"
  : > "$dir/nvidia-smi-compute-poll.log"
  started="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  set +e
  PYTHONPATH="$WORKTREE/src:$WORKTREE/scripts/maintenance" "$VENV/bin/python" "$REPLAY_RUNNER" \
    --device cuda --snapshot "$SNAP" --out-dir "$dir" --source-head "$SOURCE_HEAD" \
    --lock-sha256 "$EXPECTED_LOCK_SHA" --snapshot-manifest-sha256 "$EXPECTED_SNAPSHOT_MANIFEST_SHA" \
    --formal-runner-sha256 "$FORMAL_RUNNER_SHA" --replay-runner-sha256 "$REPLAY_RUNNER_SHA" \
    --shell-sha256 "$SHELL_SHA" --gpu-uuid "$GPU_UUID" >"$dir/stdout.txt" 2>"$dir/stderr.txt" &
  pid=$!
  set -e
  printf '%s\n' "$pid" > "$dir/provider-pid.txt"
  visible=false
  peak=0
  while proc_is_running_non_zombie "$pid"; do
    snapshot="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
    {
      echo "[$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')]"
      printf '%s\n' "$snapshot"
    } >> "$dir/nvidia-smi-compute-poll.log"
    match="$(printf '%s\n' "$snapshot" | awk -F',' -v p="$pid" '{x=$1; u=$2; m=$3; gsub(/[[:space:]]/,"",x); gsub(/^[[:space:]]+|[[:space:]]+$/,"",u); gsub(/[[:space:]]/,"",m); if(x==p){print u "," m; exit}}')"
    if [[ -n "$match" ]]; then
      visible=true
      match_uuid="${match%%,*}"
      match_mem="${match##*,}"
      [[ "$match_uuid" == "$GPU_UUID" ]] || fail "$label provider appeared on unexpected GPU UUID $match_uuid"
      if [[ "$match_mem" =~ ^[0-9]+$ ]] && (( match_mem > peak )); then peak="$match_mem"; fi
    fi
    sleep 0.2
  done
  set +e
  wait "$pid"
  rc=$?
  set -e
  ended="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  printf '%s\n' "$rc" > "$dir/exitcode.txt"
  printf '%s\n' "$started" > "$dir/started_at_utc.txt"
  printf '%s\n' "$ended" > "$dir/ended_at_utc.txt"
  [[ "$rc" == '0' ]] || { tail -n 120 "$dir/stderr.txt" || true; fail "$label failed rc=$rc" "$rc"; }
  [[ "$visible" == 'true' ]] || fail "$label PID was never visible in nvidia-smi"
  (( peak > 0 )) || fail "$label provider VRAM peak not observed"
  sleep 2
  nvidia-smi -i "$GPU_INDEX" --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version --format=csv,noheader,nounits > "$dir/gpu-after.csv"
  local after_apps
  after_apps="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
  printf '%s\n' "$after_apps" > "$dir/nvidia-smi-compute-after.txt"
  if printf '%s\n' "$after_apps" | awk -F',' -v p="$pid" '{x=$1; gsub(/[[:space:]]/,"",x); if(x==p)f=1} END{exit(f?0:1)}'; then
    fail "$label PID still present after exit"
  fi
  after="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
  [[ "$after" =~ ^[0-9]+$ ]] || fail "$label invalid post-run VRAM"
  delta=$(( after - before )); (( delta < 0 )) && delta=$(( -delta ))
  (( delta <= VRAM_RELEASE_TOLERANCE_MIB )) || fail "$label VRAM did not return near baseline"
  LABEL="$label" DIR="$dir" PID="$pid" GPU_UUID="$GPU_UUID" BEFORE="$before" PEAK="$peak" AFTER="$after" TOL="$VRAM_RELEASE_TOLERANCE_MIB" python3 - <<'PY'
import json, os
from pathlib import Path
p = Path(os.environ['DIR']) / 'external-gpu-evidence.json'
p.write_text(json.dumps({
  'label': os.environ['LABEL'],
  'provider_pid': int(os.environ['PID']),
  'provider_pid_visible_in_nvidia_smi': True,
  'provider_pid_released_after_exit': True,
  'gpu_uuid': os.environ['GPU_UUID'],
  'vram_before_total_mib': int(os.environ['BEFORE']),
  'vram_peak_provider_mib': int(os.environ['PEAK']),
  'vram_after_total_mib': int(os.environ['AFTER']),
  'vram_release_tolerance_mib': int(os.environ['TOL']),
  'vram_released': True,
}, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY
  echo "PASS $label pid=$pid peak=${peak}MiB"
}

printf '\n=== 5. CUDA replay: two independent processes ===\n'
run_cuda cuda-a
run_cuda cuda-b

printf '\n=== 6. Compare independent-process replay identities ===\n'
LOCAL_OUT="$LOCAL_OUT" SOURCE_HEAD="$SOURCE_HEAD" EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" \
FORMAL_RUNNER_SHA="$FORMAL_RUNNER_SHA" REPLAY_RUNNER_SHA="$REPLAY_RUNNER_SHA" SHELL_SHA="$SHELL_SHA" python3 - <<'PY'
from __future__ import annotations
import json, math, os
from pathlib import Path
root = Path(os.environ['LOCAL_OUT'])
labels = ('cpu-a','cpu-b','cuda-a','cuda-b')
runs = {label: json.loads((root/label/'result.json').read_text(encoding='utf-8')) for label in labels}
pids = [runs[x]['pid'] for x in labels]
if len(set(pids)) != 4:
    raise SystemExit(f'provider PIDs are not all distinct: {pids}')
for label, row in runs.items():
    if row.get('status') != 'PASS' or row.get('serialized_model_state') is not False:
        raise SystemExit(f'{label}: invalid replay status/state evidence')
    if row.get('source_head_sha') != os.environ['SOURCE_HEAD']:
        raise SystemExit(f'{label}: source head mismatch')
    if row.get('dependency_lock_sha256') != os.environ['EXPECTED_LOCK_SHA']:
        raise SystemExit(f'{label}: lock mismatch')
    if row.get('formal_runner_sha256') != os.environ['FORMAL_RUNNER_SHA']:
        raise SystemExit(f'{label}: formal runner mismatch')
    if row.get('replay_runner_sha256') != os.environ['REPLAY_RUNNER_SHA']:
        raise SystemExit(f'{label}: replay runner mismatch')
    if row.get('shell_sha256') != os.environ['SHELL_SHA']:
        raise SystemExit(f'{label}: shell mismatch')
    if not row.get('finite_predictions') or row.get('holdout_accessed') or row.get('prospective_accessed'):
        raise SystemExit(f'{label}: invalid prediction/data-boundary evidence')

def compare(a: str, b: str) -> dict:
    x, y = runs[a], runs[b]
    fields = ('request_sha256','input_series_sha256_f32','prediction_sha256_f32','chronology_mapping_sha256','output_shape','game','time_axis','horizon','target_layout','seed','model_revision','weight_sha256','snapshot_manifest_sha256')
    mismatches = [f for f in fields if x.get(f) != y.get(f)]
    if mismatches:
        raise SystemExit(f'{a}/{b}: replay identity mismatch: {mismatches}')
    return {
      'run_a': a, 'run_b': b, 'pid_a': x['pid'], 'pid_b': y['pid'],
      'distinct_pids': x['pid'] != y['pid'],
      'request_sha256_equal': True, 'input_sha256_equal': True,
      'prediction_sha256_equal': True, 'exact_replay': True,
      'prediction_sha256': x['prediction_sha256_f32'],
    }
cpu_cmp = compare('cpu-a','cpu-b')
cuda_cmp = compare('cuda-a','cuda-b')
for label in ('cuda-a','cuda-b'):
    ext = json.loads((root/label/'external-gpu-evidence.json').read_text(encoding='utf-8'))
    if not all(ext.get(k) is True for k in ('provider_pid_visible_in_nvidia_smi','provider_pid_released_after_exit','vram_released')):
        raise SystemExit(f'{label}: incomplete external CUDA evidence')
summary = {
  'schema_version': 'timer-base-84m.separate-process-replay.v1',
  'status': 'PASS',
  'process_count': 4,
  'all_provider_pids_distinct': True,
  'cpu_replay': cpu_cmp,
  'cuda_replay': cuda_cmp,
  'same_device_exact_prediction_sha_required': True,
  'numerical_tolerance_used': False,
  'serialized_model_state': False,
  'synthetic_input_only': True,
  'holdout_accessed': False,
  'prospective_accessed': False,
  'source_head_sha': os.environ['SOURCE_HEAD'],
  'dependency_lock_sha256': os.environ['EXPECTED_LOCK_SHA'],
  'formal_runner_sha256': os.environ['FORMAL_RUNNER_SHA'],
  'replay_runner_sha256': os.environ['REPLAY_RUNNER_SHA'],
  'shell_sha256': os.environ['SHELL_SHA'],
}
(root/'replay-summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n', encoding='utf-8')
print(json.dumps(summary, indent=2, sort_keys=True))
PY

printf '\n=== 7. Build replay artifact manifest and SHA256SUMS ===\n'
LOCAL_OUT="$LOCAL_OUT" python3 - <<'PY'
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
root = Path(os.environ['LOCAL_OUT'])
manifest=[]
for path in sorted(root.rglob('*')):
    if not path.is_file() or path.name in {'ARTIFACT_MANIFEST.json','SHA256SUMS'}:
        continue
    rel=path.relative_to(root).as_posix(); data=path.read_bytes()
    manifest.append({'path':rel,'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(root/'ARTIFACT_MANIFEST.json').write_text(json.dumps({'schema_version':'timer-base-84m.replay-artifact-manifest.v1','artifact_count':len(manifest),'artifacts':manifest},indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY
(
  cd "$LOCAL_OUT"
  find . -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf '\n=== 8. Promote, race-check, commit, and push replay evidence ===\n'
mkdir -p "$OUT"
cp -a "$LOCAL_OUT/." "$OUT/"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved during replay; push aborted'
git add "$OUT"
STAGED="$(git diff --cached --name-only)"
[[ -n "$STAGED" ]] || fail 'no replay evidence staged'
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in "$OUT"/*) ;; *) fail "unexpected staged path: $path" ;; esac
done <<< "$STAGED"
git diff --exit-code "origin/main" -- pyproject.toml uv.lock || fail 'root dependency files changed'
git commit -m 'evidence(timer): add separate-process replay'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved after replay commit; push aborted'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote replay evidence head mismatch after push'

printf '\n============================================================\n'
echo 'STATUS=SEPARATE_PROCESS_REPLAY_EVIDENCE_PUSHED'
echo "RUN_ID=$RUN_ID"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo 'PROCESS_COUNT=4'
echo 'CPU_INDEPENDENT_PROCESSES=2'
echo 'CUDA_INDEPENDENT_PROCESSES=2'
echo 'SAME_DEVICE_EXACT_PREDICTION_SHA=true'
echo 'NUMERICAL_TOLERANCE_USED=false'
echo 'ALL_PROVIDER_PIDS_DISTINCT=true'
echo 'HOLDOUT_ACCESSED=false'
echo 'PROSPECTIVE_ACCESSED=false'
echo 'NEXT=PROVIDER_IMPLEMENTATION_AND_REPOSITORY_VERIFICATION'
echo '============================================================'
