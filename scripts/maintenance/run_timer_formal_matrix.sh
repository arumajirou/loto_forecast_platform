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
RUNNER="scripts/maintenance/timer_formal_matrix_runner.py"
SELF="scripts/maintenance/run_timer_formal_matrix.sh"
RUN_ID="timer-formal-matrix-$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="audit/local-runs/$RUN_ID"
LOCAL_OUT="$EVIDENCE/$RUN_ID"
mkdir -p "$LOCAL_OUT"

printf '=== 1. Synchronize exact PR head and verify clean worktree ===\n'
git fetch origin "$HEAD_REF" main
SOURCE_HEAD="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$SOURCE_HEAD" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before formal matrix'
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Reverify approval, lock, runner, and exact snapshot ===\n'
for f in "$APPROVAL_RECORD" "$REMOTE_REVIEW" "$DEP_REVIEW" "$LOCK" "$RUNNER" "$SELF"; do
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

printf '\n=== 3. Compile matrix runner before any model load ===\n'
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" -m py_compile "$RUNNER" || fail 'matrix runner Python syntax check failed'
RUNNER_SHA="$(sha256sum "$RUNNER" | awk '{print $1}')"
SHELL_SHA="$(sha256sum "$SELF" | awk '{print $1}')"
echo "RUNNER_SHA256=$RUNNER_SHA"
echo "SHELL_SHA256=$SHELL_SHA"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONHASHSEED=1
export HF_HOME="$HOME/.cache/loto/timer-base-84m/hf-offline"
mkdir -p "$HF_HOME"

printf '\n=== 4. Execute formal CPU matrix: 120 cases ===\n'
CPU_STARTED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
set +e
CUDA_VISIBLE_DEVICES='' PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" "$RUNNER" \
  --device cpu \
  --snapshot "$SNAP" \
  --out-dir "$LOCAL_OUT" \
  --source-head "$SOURCE_HEAD" \
  --lock-sha256 "$EXPECTED_LOCK_SHA" \
  --snapshot-manifest-sha256 "$EXPECTED_SNAPSHOT_MANIFEST_SHA" \
  --runner-sha256 "$RUNNER_SHA" \
  --shell-sha256 "$SHELL_SHA" \
  >"$LOCAL_OUT/cpu-stdout.txt" 2>"$LOCAL_OUT/cpu-stderr.txt"
CPU_RC=$?
set -e
CPU_ENDED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '%s\n' "$CPU_RC" > "$LOCAL_OUT/cpu-exitcode.txt"
printf '%s\n' "$CPU_STARTED" > "$LOCAL_OUT/cpu-started_at_utc.txt"
printf '%s\n' "$CPU_ENDED" > "$LOCAL_OUT/cpu-ended_at_utc.txt"
if [[ "$CPU_RC" != '0' ]]; then
  echo '--- CPU stdout ---'; tail -n 80 "$LOCAL_OUT/cpu-stdout.txt" || true
  echo '--- CPU stderr ---'; tail -n 120 "$LOCAL_OUT/cpu-stderr.txt" || true
  fail "formal CPU matrix failed rc=$CPU_RC" "$CPU_RC"
fi
[[ -f "$LOCAL_OUT/cpu-summary.raw.json" ]] || fail 'CPU summary missing'
echo 'PASS FORMAL_CPU_MATRIX'
cat "$LOCAL_OUT/cpu-summary.raw.json"

printf '\n=== 5. CUDA preflight and baseline evidence ===\n'
command -v nvidia-smi >/dev/null 2>&1 || fail 'nvidia-smi is not available'
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit('torch.cuda.is_available() is false')
if torch.cuda.device_count() < 1:
    raise SystemExit('no CUDA device is visible')
print('PASS TORCH_CUDA_AVAILABLE')
print('CUDA_DEVICE_NAME=' + torch.cuda.get_device_name(0))
print('TORCH_CUDA_BUILD=' + str(torch.version.cuda))
PY
nvidia-smi -i "$GPU_INDEX" \
  --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version \
  --format=csv,noheader,nounits > "$LOCAL_OUT/gpu-before.csv"
cat "$LOCAL_OUT/gpu-before.csv"
GPU_UUID="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=uuid --format=csv,noheader | head -n1 | tr -d '[:space:]')"
VRAM_BEFORE_MIB="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
VRAM_FREE_BEFORE_MIB="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.free --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
[[ "$VRAM_BEFORE_MIB" =~ ^[0-9]+$ ]] || fail "invalid baseline VRAM used: $VRAM_BEFORE_MIB"
[[ "$VRAM_FREE_BEFORE_MIB" =~ ^[0-9]+$ ]] || fail "invalid baseline VRAM free: $VRAM_FREE_BEFORE_MIB"
(( VRAM_FREE_BEFORE_MIB >= VRAM_MIN_FREE_MIB )) || fail "insufficient free VRAM for certified matrix: ${VRAM_FREE_BEFORE_MIB} MiB < ${VRAM_MIN_FREE_MIB} MiB"
echo "GPU_UUID=$GPU_UUID"
echo "VRAM_BEFORE_MIB=$VRAM_BEFORE_MIB"
echo "VRAM_FREE_BEFORE_MIB=$VRAM_FREE_BEFORE_MIB"

printf '\n=== 6. Execute formal CUDA matrix: 120 cases ===\n'
CUDA_STARTED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
: > "$LOCAL_OUT/cuda-nvidia-smi-compute-poll.log"
set +e
PYTHONPATH="$WORKTREE/src" "$VENV/bin/python" "$RUNNER" \
  --device cuda \
  --snapshot "$SNAP" \
  --out-dir "$LOCAL_OUT" \
  --source-head "$SOURCE_HEAD" \
  --lock-sha256 "$EXPECTED_LOCK_SHA" \
  --snapshot-manifest-sha256 "$EXPECTED_SNAPSHOT_MANIFEST_SHA" \
  --runner-sha256 "$RUNNER_SHA" \
  --shell-sha256 "$SHELL_SHA" \
  --gpu-uuid "$GPU_UUID" \
  >"$LOCAL_OUT/cuda-stdout.txt" 2>"$LOCAL_OUT/cuda-stderr.txt" &
CUDA_PID=$!
set -e
printf '%s\n' "$CUDA_PID" > "$LOCAL_OUT/cuda-provider-pid.txt"
echo "CUDA_PROVIDER_PID=$CUDA_PID"
CUDA_PROVIDER_VISIBLE=false
VRAM_PEAK_PROVIDER_MIB=0

cleanup_cuda_provider() {
  if proc_is_running_non_zombie "$CUDA_PID"; then
    kill "$CUDA_PID" 2>/dev/null || true
    wait "$CUDA_PID" 2>/dev/null || true
  fi
}
trap cleanup_cuda_provider EXIT INT TERM

while proc_is_running_non_zombie "$CUDA_PID"; do
  TS="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"
  SNAPSHOT="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
  {
    echo "[$TS]"
    printf '%s\n' "$SNAPSHOT"
  } >> "$LOCAL_OUT/cuda-nvidia-smi-compute-poll.log"
  MATCH="$(printf '%s\n' "$SNAPSHOT" | awk -F',' -v p="$CUDA_PID" '
    {
      pid=$1; uuid=$2; mem=$3;
      gsub(/[[:space:]]/, "", pid);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", uuid);
      gsub(/[[:space:]]/, "", mem);
      if (pid == p) { print uuid "," mem; exit }
    }
  ')"
  if [[ -n "$MATCH" ]]; then
    CUDA_PROVIDER_VISIBLE=true
    MATCH_UUID="${MATCH%%,*}"
    MATCH_MEM="${MATCH##*,}"
    [[ "$MATCH_UUID" == "$GPU_UUID" ]] || fail "matrix provider PID appeared on unexpected GPU UUID: $MATCH_UUID"
    if [[ "$MATCH_MEM" =~ ^[0-9]+$ ]] && (( MATCH_MEM > VRAM_PEAK_PROVIDER_MIB )); then
      VRAM_PEAK_PROVIDER_MIB="$MATCH_MEM"
    fi
  fi
  sleep 0.2
done

set +e
wait "$CUDA_PID"
CUDA_RC=$?
set -e
trap - EXIT INT TERM
CUDA_ENDED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '%s\n' "$CUDA_RC" > "$LOCAL_OUT/cuda-exitcode.txt"
printf '%s\n' "$CUDA_STARTED" > "$LOCAL_OUT/cuda-started_at_utc.txt"
printf '%s\n' "$CUDA_ENDED" > "$LOCAL_OUT/cuda-ended_at_utc.txt"
if [[ "$CUDA_RC" != '0' ]]; then
  echo '--- CUDA stdout ---'; tail -n 80 "$LOCAL_OUT/cuda-stdout.txt" || true
  echo '--- CUDA stderr ---'; tail -n 120 "$LOCAL_OUT/cuda-stderr.txt" || true
  fail "formal CUDA matrix failed rc=$CUDA_RC" "$CUDA_RC"
fi
[[ "$CUDA_PROVIDER_VISIBLE" == 'true' ]] || fail 'formal CUDA matrix provider PID was never visible in nvidia-smi'
(( VRAM_PEAK_PROVIDER_MIB > 0 )) || fail 'formal CUDA matrix provider VRAM peak was not observed'
[[ -f "$LOCAL_OUT/cuda-summary.raw.json" ]] || fail 'CUDA summary missing'
echo "PASS CUDA_PROVIDER_PID_VISIBLE_IN_NVIDIA_SMI pid=$CUDA_PID"
echo "VRAM_PEAK_PROVIDER_MIB=$VRAM_PEAK_PROVIDER_MIB"

printf '\n=== 7. Verify CUDA provider exit and VRAM release ===\n'
sleep 2
nvidia-smi -i "$GPU_INDEX" \
  --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version \
  --format=csv,noheader,nounits > "$LOCAL_OUT/gpu-after.csv"
VRAM_AFTER_MIB="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
AFTER_APPS="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
printf '%s\n' "$AFTER_APPS" > "$LOCAL_OUT/cuda-nvidia-smi-compute-after.txt"
if printf '%s\n' "$AFTER_APPS" | awk -F',' -v p="$CUDA_PID" '{pid=$1; gsub(/[[:space:]]/, "", pid); if (pid==p) found=1} END{exit(found?0:1)}'; then
  fail 'CUDA matrix provider PID still present in nvidia-smi after exit'
fi
[[ "$VRAM_AFTER_MIB" =~ ^[0-9]+$ ]] || fail "invalid post-run VRAM value: $VRAM_AFTER_MIB"
VRAM_DELTA=$(( VRAM_AFTER_MIB - VRAM_BEFORE_MIB ))
if (( VRAM_DELTA < 0 )); then VRAM_DELTA=$(( -VRAM_DELTA )); fi
(( VRAM_DELTA <= VRAM_RELEASE_TOLERANCE_MIB )) || fail "aggregate VRAM did not return near baseline: before=$VRAM_BEFORE_MIB after=$VRAM_AFTER_MIB delta=$VRAM_DELTA"
echo 'PASS CUDA_PROVIDER_PID_RELEASED'
echo "PASS CUDA_VRAM_RELEASE before=$VRAM_BEFORE_MIB provider_peak=$VRAM_PEAK_PROVIDER_MIB after=$VRAM_AFTER_MIB tolerance=$VRAM_RELEASE_TOLERANCE_MIB"

printf '\n=== 8. Finalize case-level external CUDA evidence and comparisons ===\n'
LOCAL_OUT="$LOCAL_OUT" GPU_UUID="$GPU_UUID" CUDA_PID="$CUDA_PID" \
VRAM_BEFORE_MIB="$VRAM_BEFORE_MIB" VRAM_PEAK_PROVIDER_MIB="$VRAM_PEAK_PROVIDER_MIB" \
VRAM_AFTER_MIB="$VRAM_AFTER_MIB" VRAM_RELEASE_TOLERANCE_MIB="$VRAM_RELEASE_TOLERANCE_MIB" \
SOURCE_HEAD="$SOURCE_HEAD" EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" \
RUNNER_SHA="$RUNNER_SHA" SHELL_SHA="$SHELL_SHA" python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

root = Path(os.environ['LOCAL_OUT'])
gpu_uuid = os.environ['GPU_UUID']
cuda_pid = int(os.environ['CUDA_PID'])
vram_before = int(os.environ['VRAM_BEFORE_MIB'])
vram_peak = int(os.environ['VRAM_PEAK_PROVIDER_MIB'])
vram_after = int(os.environ['VRAM_AFTER_MIB'])
tolerance = int(os.environ['VRAM_RELEASE_TOLERANCE_MIB'])


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        ''.join(json.dumps(row, sort_keys=True, separators=(',', ':')) + '\n' for row in rows),
        encoding='utf-8',
    )

cpu_rows = read_jsonl(root / 'cpu-results.jsonl')
cuda_rows = read_jsonl(root / 'cuda-results.jsonl')
if len(cpu_rows) != 120 or len(cuda_rows) != 120:
    raise SystemExit(f'formal matrix case count mismatch cpu={len(cpu_rows)} cuda={len(cuda_rows)}')

for row in cuda_rows:
    row['provider_pid'] = cuda_pid
    row['provider_pid_visible_in_nvidia_smi'] = True
    row['provider_pid_released_after_exit'] = True
    row['gpu_uuid'] = gpu_uuid
    row['vram_before_total_mib'] = vram_before
    row['vram_peak_provider_mib'] = vram_peak
    row['vram_after_total_mib'] = vram_after
    row['vram_release_tolerance_mib'] = tolerance
    row['vram_released'] = True
    row['cpu_fallback'] = False
write_jsonl(root / 'cuda-results.jsonl', cuda_rows)

cpu_by_key = {}
cuda_by_key = {}
for row in cpu_rows:
    key = (row['game'], row['time_axis'], row['horizon'], row['target_layout'], row['seed'])
    cpu_by_key[key] = row
for row in cuda_rows:
    key = (row['game'], row['time_axis'], row['horizon'], row['target_layout'], row['seed'])
    cuda_by_key[key] = row
if cpu_by_key.keys() != cuda_by_key.keys():
    raise SystemExit('CPU/CUDA matrix keys differ')

comparisons = []
all_diffs = []
exact_hash_matches = 0
for key in sorted(cpu_by_key):
    cpu = cpu_by_key[key]
    cuda = cuda_by_key[key]
    if cpu['input_series_sha256_f32'] != cuda['input_series_sha256_f32']:
        raise SystemExit(f'cross-device input identity mismatch: {key}')
    if cpu['output_shape'] != cuda['output_shape']:
        raise SystemExit(f'cross-device output shape mismatch: {key}')
    cpu_flat = [float(v) for row in cpu['predictions'] for v in row]
    cuda_flat = [float(v) for row in cuda['predictions'] for v in row]
    if len(cpu_flat) != len(cuda_flat):
        raise SystemExit(f'cross-device prediction length mismatch: {key}')
    diffs = [abs(a - b) for a, b in zip(cpu_flat, cuda_flat, strict=True)]
    max_abs = max(diffs, default=0.0)
    mean_abs = sum(diffs) / len(diffs) if diffs else 0.0
    all_diffs.extend(diffs)
    exact = cpu['prediction_sha256_f32'] == cuda['prediction_sha256_f32']
    exact_hash_matches += int(exact)
    comparisons.append({
        'game': key[0],
        'time_axis': key[1],
        'horizon': key[2],
        'target_layout': key[3],
        'seed': key[4],
        'input_identity_equal': True,
        'output_shape_equal': True,
        'exact_prediction_sha256_equal': exact,
        'max_abs_diff': max_abs,
        'mean_abs_diff': mean_abs,
    })

cross_summary = {
    'schema_version': 'timer-base-84m.cross-device-comparison.v1',
    'status': 'RECORDED_NOT_REPLAY_GATE',
    'comparison_count': len(comparisons),
    'exact_prediction_hash_match_count': exact_hash_matches,
    'max_abs_diff_overall': max(all_diffs, default=0.0),
    'mean_abs_diff_overall': sum(all_diffs) / len(all_diffs) if all_diffs else 0.0,
    'note': 'Cross-device bit identity is not Gate F replay. Same-device independent-process replay is evaluated separately.',
    'cases': comparisons,
}
(root / 'cross-device-comparison.json').write_text(json.dumps(cross_summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')

layout_comparisons = []
for device_name, rows in [('cpu', cpu_rows), ('cuda', cuda_rows)]:
    grouped = {}
    for row in rows:
        key = (row['game'], row['time_axis'], row['horizon'], row['seed'])
        grouped.setdefault(key, {})[row['target_layout']] = row
    for key, layouts in sorted(grouped.items()):
        a = layouts['position_univariate']
        b = layouts['position_panel_batched_univariate']
        af = [float(v) for row in a['predictions'] for v in row]
        bf = [float(v) for row in b['predictions'] for v in row]
        diffs = [abs(x - y) for x, y in zip(af, bf, strict=True)]
        layout_comparisons.append({
            'device': device_name,
            'game': key[0],
            'time_axis': key[1],
            'horizon': key[2],
            'seed': key[3],
            'same_input_identity': a['input_series_sha256_f32'] == b['input_series_sha256_f32'],
            'output_shape_equal': a['output_shape'] == b['output_shape'],
            'exact_prediction_sha256_equal': a['prediction_sha256_f32'] == b['prediction_sha256_f32'],
            'max_abs_diff': max(diffs, default=0.0),
        })
(root / 'layout-comparison.json').write_text(json.dumps({
    'schema_version': 'timer-base-84m.layout-comparison.v1',
    'status': 'RECORDED',
    'comparison_count': len(layout_comparisons),
    'cases': layout_comparisons,
}, indent=2, sort_keys=True) + '\n', encoding='utf-8')

cpu_summary = json.loads((root / 'cpu-summary.raw.json').read_text(encoding='utf-8'))
cuda_summary = json.loads((root / 'cuda-summary.raw.json').read_text(encoding='utf-8'))
cuda_summary.update({
    'provider_pid': cuda_pid,
    'provider_pid_visible_in_nvidia_smi': True,
    'provider_pid_released_after_exit': True,
    'gpu_uuid': gpu_uuid,
    'vram_before_total_mib': vram_before,
    'vram_peak_provider_mib': vram_peak,
    'vram_after_total_mib': vram_after,
    'vram_release_tolerance_mib': tolerance,
    'vram_released': True,
})
(root / 'cuda-summary.json').write_text(json.dumps(cuda_summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
(root / 'cpu-summary.json').write_text(json.dumps(cpu_summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')

summary = {
    'schema_version': 'timer-base-84m.formal-runtime-matrix.v1',
    'status': 'PASS',
    'total_case_count': len(cpu_rows) + len(cuda_rows),
    'cpu_case_count': len(cpu_rows),
    'cuda_case_count': len(cuda_rows),
    'games': ['numbers3', 'numbers4', 'miniloto', 'loto6', 'loto7'],
    'time_axes': ['draw_sequence', 'calendar_time'],
    'horizons': [1, 2, 5],
    'layouts': ['position_univariate', 'position_panel_batched_univariate'],
    'seeds': [1, 7],
    'best_seed_selected': False,
    'synthetic_contract_matrix': True,
    'holdout_accessed': False,
    'prospective_accessed': False,
    'cpu_status': cpu_summary['status'],
    'cuda_status': cuda_summary['status'],
    'cuda_provider_pid_visible_in_nvidia_smi': True,
    'cuda_provider_pid_released_after_exit': True,
    'cuda_vram_released': True,
    'cross_device_comparison_status': cross_summary['status'],
    'cross_device_max_abs_diff': cross_summary['max_abs_diff_overall'],
    'source_head_sha': os.environ['SOURCE_HEAD'],
    'dependency_lock_sha256': os.environ['EXPECTED_LOCK_SHA'],
    'runner_sha256': os.environ['RUNNER_SHA'],
    'shell_sha256': os.environ['SHELL_SHA'],
}
(root / 'matrix-summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(summary, indent=2, sort_keys=True))
PY

printf '\n=== 9. Build manifest and SHA256SUMS ===\n'
LOCAL_OUT="$LOCAL_OUT" python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ['LOCAL_OUT'])
manifest = []
for path in sorted(root.iterdir(), key=lambda p: p.name):
    if not path.is_file() or path.name in {'ARTIFACT_MANIFEST.json', 'SHA256SUMS'}:
        continue
    data = path.read_bytes()
    manifest.append({'path': path.name, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
(root / 'ARTIFACT_MANIFEST.json').write_text(json.dumps({
    'schema_version': 'timer-base-84m.formal-matrix-artifact-manifest.v1',
    'artifact_count': len(manifest),
    'artifacts': manifest,
}, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY
(
  cd "$LOCAL_OUT"
  find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%P\n' | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf '\n=== 10. Promote compact matrix evidence into repository ===\n'
mkdir -p "$OUT"
cp -a "$LOCAL_OUT/." "$OUT/"

printf '\n=== 11. Race-check, strict stage scope, commit, and push ===\n'
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
[[ "$REMOTE_NOW" == "$SOURCE_HEAD" ]] || fail 'PR branch moved during formal matrix; evidence preserved locally but push aborted'
git add "$OUT"
STAGED="$(git diff --cached --name-only)"
[[ -n "$STAGED" ]] || fail 'no formal matrix evidence staged'
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    "$OUT"/*) ;;
    *) fail "unexpected staged path: $path" ;;
  esac
done <<< "$STAGED"
git diff --exit-code "origin/main" -- pyproject.toml uv.lock || fail 'root dependency files changed'
git commit -m 'evidence(timer): add formal CPU CUDA runtime matrix'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved after formal matrix commit; push aborted'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote SHA mismatch after formal matrix push'

echo
echo '============================================================'
echo 'STATUS=FORMAL_RUNTIME_MATRIX_EVIDENCE_PUSHED'
echo "RUN_ID=$RUN_ID"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo 'TOTAL_CASES=240'
echo 'CPU_CASES=120'
echo 'CUDA_CASES=120'
echo 'SEEDS=1,7'
echo 'BEST_SEED_SELECTED=false'
echo "GPU_UUID=$GPU_UUID"
echo "CUDA_PROVIDER_PID=$CUDA_PID"
echo "VRAM_BEFORE_MIB=$VRAM_BEFORE_MIB"
echo "VRAM_PEAK_PROVIDER_MIB=$VRAM_PEAK_PROVIDER_MIB"
echo "VRAM_AFTER_MIB=$VRAM_AFTER_MIB"
echo 'HOLDOUT_ACCESSED=false'
echo 'PROSPECTIVE_ACCESSED=false'
echo 'NEXT=SEPARATE_PROCESS_REPLAY'
echo '============================================================'
