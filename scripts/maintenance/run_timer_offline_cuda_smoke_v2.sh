#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_PACKET_SHA='0d7800ae8b70274b034cc5a37893ae806b21f0bee8da5854a470ffe257491512'
REV='70077a71acce1b4c00d98332fcaabc694255d8e5'
GPU_INDEX='0'
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
RUN_ID="timer-cuda-smoke-$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="audit/local-runs/$RUN_ID"
LOCAL_OUT="$EVIDENCE/$RUN_ID"
mkdir -p "$LOCAL_OUT"

printf '=== 1. Synchronize and bind exact source head ===\n'
git fetch origin "$HEAD_REF" main
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
SOURCE_HEAD="$(git rev-parse HEAD)"
[[ "$SOURCE_HEAD" == "$(git rev-parse "origin/$HEAD_REF")" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before CUDA smoke'
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Enforce named-human approval and frozen lock ===\n'
for f in "$APPROVAL_RECORD" "$REMOTE_REVIEW" "$DEP_REVIEW" "$LOCK"; do
  [[ -f "$f" ]] || fail "missing required approval/lock artifact: $f"
done
[[ -x "$VENV/bin/python" ]] || fail 'isolated Timer Python environment missing'
[[ -d "$SNAP" ]] || fail 'pinned local snapshot missing'

APPROVAL_RECORD="$APPROVAL_RECORD" REMOTE_REVIEW="$REMOTE_REVIEW" DEP_REVIEW="$DEP_REVIEW" \
EXPECTED_LOCK_SHA="$EXPECTED_LOCK_SHA" EXPECTED_PACKET_SHA="$EXPECTED_PACKET_SHA" \
python3 - <<'PY'
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
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$EXPECTED_LOCK_SHA" ]] || fail 'isolated lock SHA changed'
echo 'PASS LOCK_SHA256'

printf '\n=== 3. Reverify exact pinned snapshot immediately before load ===\n'
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

printf '\n=== 4. Preflight live CUDA device and baseline VRAM ===\n'
command -v nvidia-smi >/dev/null 2>&1 || fail 'nvidia-smi is not available'
export CUDA_VISIBLE_DEVICES="$GPU_INDEX"
"$VENV/bin/python" - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit('torch.cuda.is_available() is false')
if torch.cuda.device_count() < 1:
    raise SystemExit('no CUDA device is visible')
print('PASS TORCH_CUDA_AVAILABLE')
print('CUDA_DEVICE_NAME=' + torch.cuda.get_device_name(0))
print('TORCH_CUDA_BUILD=' + str(torch.version.cuda))
PY
nvidia-smi -i "$GPU_INDEX" --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version --format=csv,noheader,nounits > "$LOCAL_OUT/gpu-before.csv"
cat "$LOCAL_OUT/gpu-before.csv"
GPU_UUID="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=uuid --format=csv,noheader | head -n1 | tr -d '[:space:]')"
VRAM_BEFORE_MIB="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
[[ -n "$GPU_UUID" ]] || fail 'empty GPU UUID'
[[ "$VRAM_BEFORE_MIB" =~ ^[0-9]+$ ]] || fail "invalid baseline VRAM value: $VRAM_BEFORE_MIB"
echo "GPU_UUID=$GPU_UUID"
echo "VRAM_BEFORE_MIB=$VRAM_BEFORE_MIB"

printf '\n=== 5. Execute frozen/offline CUDA load + deterministic predict smoke ===\n'
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONHASHSEED=1
export HF_HOME="$HOME/.cache/loto/timer-base-84m/hf-offline"
mkdir -p "$HF_HOME"

cat > "$LOCAL_OUT/provider-runner.py" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def _deny_network(*args, **kwargs):
    raise RuntimeError('NETWORK_ACCESS_BLOCKED_BY_TIMER_CUDA_SMOKE')

socket.create_connection = _deny_network
socket.socket.connect = _deny_network

import torch
import transformers
from transformers import AutoModelForCausalLM

snap = Path(os.environ['SNAP']).resolve()
out_json = Path(os.environ['OUT_JSON'])
ready_file = Path(os.environ['READY_FILE'])
started_at = os.environ['STARTED_AT']
expected_gpu_uuid = os.environ['EXPECTED_GPU_UUID']

torch.manual_seed(1)
torch.cuda.manual_seed_all(1)
torch.set_grad_enabled(False)
torch.cuda.set_device(0)
torch.cuda.empty_cache()
torch.cuda.reset_peak_memory_stats(0)

model = AutoModelForCausalLM.from_pretrained(
    str(snap),
    trust_remote_code=True,
    local_files_only=True,
    torch_dtype=torch.float32,
)
model.eval()
model.to('cuda:0')
torch.cuda.synchronize(0)
params = list(model.parameters())
buffers = list(model.buffers())
parameter_count = sum(p.numel() for p in params)
finite_parameters = all(bool(torch.isfinite(p).all().item()) for p in params)
finite_buffers = all(bool(torch.isfinite(b).all().item()) for b in buffers if b.is_floating_point())
model_device = str(params[0].device) if params else 'cuda:0'
if not model_device.startswith('cuda'):
    raise RuntimeError(f'model is not on CUDA: {model_device}')
x = torch.linspace(-1.0, 1.0, steps=96, dtype=torch.float32, device='cuda:0').reshape(1, 96)
if not str(x.device).startswith('cuda'):
    raise RuntimeError(f'input tensor is not on CUDA: {x.device}')
ready_file.write_text(json.dumps({'pid': os.getpid(), 'model_device': model_device, 'input_device': str(x.device)}) + '\n', encoding='utf-8')
time.sleep(3.0)
with torch.inference_mode():
    y = model.generate(x, max_new_tokens=1)
torch.cuda.synchronize(0)
if y.ndim != 2 or y.shape[0] != 1:
    raise RuntimeError(f'unexpected output shape: {tuple(y.shape)}')
if not str(y.device).startswith('cuda'):
    raise RuntimeError(f'output tensor is not on CUDA: {y.device}')
if not bool(torch.isfinite(y).all().item()):
    raise RuntimeError('non-finite CUDA smoke output')
raw = y.detach().cpu().contiguous().numpy().tobytes()
prediction_sha256 = hashlib.sha256(raw).hexdigest()
props = torch.cuda.get_device_properties(0)
payload = {
    'schema_version': 'timer-base-84m.offline-cuda-smoke.v2',
    'status': 'PASS',
    'source_head_sha': os.environ['SOURCE_HEAD'],
    'started_at_utc': started_at,
    'ended_at_utc': datetime.now(timezone.utc).isoformat(),
    'pid': os.getpid(),
    'python': sys.version.split()[0],
    'platform': platform.platform(),
    'torch': torch.__version__,
    'torch_cuda_build': torch.version.cuda,
    'transformers': transformers.__version__,
    'model_class': model.__class__.__name__,
    'parameter_count': parameter_count,
    'finite_parameters': finite_parameters,
    'finite_float_buffers': finite_buffers,
    'requested_device': 'cuda',
    'effective_device': model_device,
    'model_on_cuda': model_device.startswith('cuda'),
    'input_device': str(x.device),
    'output_device': str(y.device),
    'cpu_fallback': False,
    'input_shape': list(x.shape),
    'output_shape': list(y.shape),
    'prediction_sha256': prediction_sha256,
    'network_policy': 'HF/Transformers offline + local_files_only + Python socket deny guard',
    'snapshot_path': str(snap),
    'synthetic_input_only': True,
    'holdout_accessed': False,
    'prospective_accessed': False,
    'gpu_uuid_expected_from_nvidia_smi': expected_gpu_uuid,
    'cuda_device_name': props.name,
    'torch_peak_memory_allocated_bytes': int(torch.cuda.max_memory_allocated(0)),
    'torch_peak_memory_reserved_bytes': int(torch.cuda.max_memory_reserved(0)),
}
if not finite_parameters or not finite_buffers:
    raise RuntimeError('non-finite model parameter/buffer detected')
out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True))
time.sleep(2.0)
PY

STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
READY_FILE="$LOCAL_OUT/provider-ready.json"
RAW_RUNTIME="$LOCAL_OUT/runtime.raw.json"
: > "$LOCAL_OUT/nvidia-smi-compute-poll.log"
SNAP="$SNAP" OUT_JSON="$RAW_RUNTIME" READY_FILE="$READY_FILE" SOURCE_HEAD="$SOURCE_HEAD" STARTED_AT="$STARTED_AT" EXPECTED_GPU_UUID="$GPU_UUID" \
  "$VENV/bin/python" "$LOCAL_OUT/provider-runner.py" >"$LOCAL_OUT/stdout.txt" 2>"$LOCAL_OUT/stderr.txt" &
PROVIDER_PID=$!
echo "$PROVIDER_PID" > "$LOCAL_OUT/provider-pid.txt"
echo "PROVIDER_PID=$PROVIDER_PID"
PROVIDER_VISIBLE=false
VRAM_PEAK_PROVIDER_MIB=0

cleanup_provider() {
  if kill -0 "$PROVIDER_PID" 2>/dev/null; then
    kill "$PROVIDER_PID" 2>/dev/null || true
    wait "$PROVIDER_PID" 2>/dev/null || true
  fi
}
trap cleanup_provider EXIT INT TERM

while true; do
  PROC_STAT="$(ps -o stat= -p "$PROVIDER_PID" 2>/dev/null | tr -d '[:space:]' || true)"
  [[ -z "$PROC_STAT" ]] && break
  [[ "$PROC_STAT" == Z* ]] && break
  TS="$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')"
  SNAPSHOT="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
  {
    echo "[$TS]"
    printf '%s\n' "$SNAPSHOT"
  } >> "$LOCAL_OUT/nvidia-smi-compute-poll.log"
  MATCH="$(printf '%s\n' "$SNAPSHOT" | awk -F',' -v p="$PROVIDER_PID" '
    {
      pid=$1; uuid=$2; mem=$3;
      gsub(/[[:space:]]/, "", pid);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", uuid);
      gsub(/[[:space:]]/, "", mem);
      if (pid == p) { print uuid "," mem; exit }
    }
  ')"
  if [[ -n "$MATCH" ]]; then
    PROVIDER_VISIBLE=true
    MATCH_UUID="${MATCH%%,*}"
    MATCH_MEM="${MATCH##*,}"
    [[ "$MATCH_UUID" == "$GPU_UUID" ]] || fail "provider PID appeared on unexpected GPU UUID: $MATCH_UUID"
    if [[ "$MATCH_MEM" =~ ^[0-9]+$ ]] && (( MATCH_MEM > VRAM_PEAK_PROVIDER_MIB )); then
      VRAM_PEAK_PROVIDER_MIB="$MATCH_MEM"
    fi
  fi
  sleep 0.2
done

set +e
wait "$PROVIDER_PID"
RC=$?
set -e
trap - EXIT INT TERM
ENDED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '%s\n' "$RC" > "$LOCAL_OUT/exitcode.txt"
printf '%s\n' "$STARTED_AT" > "$LOCAL_OUT/started_at_utc.txt"
printf '%s\n' "$ENDED_AT" > "$LOCAL_OUT/ended_at_utc.txt"
[[ "$RC" == '0' ]] || {
  echo '--- stdout ---'; cat "$LOCAL_OUT/stdout.txt" || true
  echo '--- stderr ---'; cat "$LOCAL_OUT/stderr.txt" || true
  fail "offline CUDA smoke failed rc=$RC" "$RC"
}
[[ -f "$RAW_RUNTIME" ]] || fail 'CUDA smoke runtime output missing'
[[ "$PROVIDER_VISIBLE" == 'true' ]] || fail 'provider PID was never visible in nvidia-smi compute-apps'
(( VRAM_PEAK_PROVIDER_MIB > 0 )) || fail 'provider PID had no measurable external VRAM allocation'
echo "PASS PROVIDER_PID_VISIBLE_IN_NVIDIA_SMI pid=$PROVIDER_PID"
echo "VRAM_PEAK_PROVIDER_MIB=$VRAM_PEAK_PROVIDER_MIB"

printf '\n=== 6. Verify provider exit and VRAM release ===\n'
sleep 2
AFTER_PROCESSES="$(nvidia-smi --query-compute-apps=pid,gpu_uuid,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null || true)"
printf '%s\n' "$AFTER_PROCESSES" > "$LOCAL_OUT/nvidia-smi-compute-after.txt"
if printf '%s\n' "$AFTER_PROCESSES" | awk -F',' -v p="$PROVIDER_PID" '{x=$1; gsub(/[[:space:]]/, "", x); if (x == p) found=1} END{exit found ? 0 : 1}'; then
  fail 'provider PID still appears in nvidia-smi after process exit'
fi
VRAM_AFTER_MIB="$(nvidia-smi -i "$GPU_INDEX" --query-gpu=memory.used --format=csv,noheader,nounits | head -n1 | tr -d '[:space:]')"
[[ "$VRAM_AFTER_MIB" =~ ^[0-9]+$ ]] || fail "invalid post-exit VRAM value: $VRAM_AFTER_MIB"
nvidia-smi -i "$GPU_INDEX" --query-gpu=index,uuid,name,memory.total,memory.used,memory.free,driver_version --format=csv,noheader,nounits > "$LOCAL_OUT/gpu-after.csv"
cat "$LOCAL_OUT/gpu-after.csv"
VRAM_LIMIT_MIB=$(( VRAM_BEFORE_MIB + VRAM_RELEASE_TOLERANCE_MIB ))
(( VRAM_AFTER_MIB <= VRAM_LIMIT_MIB )) || fail "aggregate VRAM did not return within ${VRAM_RELEASE_TOLERANCE_MIB} MiB of baseline: before=$VRAM_BEFORE_MIB after=$VRAM_AFTER_MIB"
echo 'PASS PROVIDER_PID_RELEASED'
echo "PASS VRAM_RELEASE before=$VRAM_BEFORE_MIB provider_peak=$VRAM_PEAK_PROVIDER_MIB after=$VRAM_AFTER_MIB tolerance=$VRAM_RELEASE_TOLERANCE_MIB"

printf '\n=== 7. Finalize compact CUDA evidence ===\n'
RAW_RUNTIME="$RAW_RUNTIME" FINAL_RUNTIME="$LOCAL_OUT/runtime.json" GPU_UUID="$GPU_UUID" PROVIDER_PID="$PROVIDER_PID" PROVIDER_VISIBLE="$PROVIDER_VISIBLE" \
VRAM_BEFORE_MIB="$VRAM_BEFORE_MIB" VRAM_PEAK_PROVIDER_MIB="$VRAM_PEAK_PROVIDER_MIB" VRAM_AFTER_MIB="$VRAM_AFTER_MIB" VRAM_RELEASE_TOLERANCE_MIB="$VRAM_RELEASE_TOLERANCE_MIB" \
python3 - <<'PY'
import json
import os
from pathlib import Path
p = json.loads(Path(os.environ['RAW_RUNTIME']).read_text(encoding='utf-8'))
if p.get('pid') != int(os.environ['PROVIDER_PID']):
    raise SystemExit('runtime PID does not match externally monitored provider PID')
if p.get('requested_device') != 'cuda' or not str(p.get('effective_device', '')).startswith('cuda'):
    raise SystemExit('runtime effective CUDA device check failed')
if p.get('model_on_cuda') is not True or p.get('cpu_fallback') is not False:
    raise SystemExit('runtime CUDA/no-fallback semantics failed')
p['gpu_uuid'] = os.environ['GPU_UUID']
p['provider_pid_visible_in_nvidia_smi'] = os.environ['PROVIDER_VISIBLE'] == 'true'
p['provider_pid_released_after_exit'] = True
p['vram_before_total_mib'] = int(os.environ['VRAM_BEFORE_MIB'])
p['vram_peak_provider_mib'] = int(os.environ['VRAM_PEAK_PROVIDER_MIB'])
p['vram_after_total_mib'] = int(os.environ['VRAM_AFTER_MIB'])
p['vram_release_tolerance_mib'] = int(os.environ['VRAM_RELEASE_TOLERANCE_MIB'])
p['vram_released'] = p['vram_after_total_mib'] <= p['vram_before_total_mib'] + p['vram_release_tolerance_mib']
Path(os.environ['FINAL_RUNTIME']).write_text(json.dumps(p, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY
cat "$LOCAL_OUT/runtime.json"

mkdir -p "$OUT"
for f in runtime.json provider-runner.py provider-pid.txt provider-ready.json stdout.txt stderr.txt exitcode.txt started_at_utc.txt ended_at_utc.txt snapshot-verify.txt gpu-before.csv gpu-after.csv nvidia-smi-compute-poll.log nvidia-smi-compute-after.txt; do
  [[ -f "$LOCAL_OUT/$f" ]] || fail "missing CUDA evidence file: $f"
  cp "$LOCAL_OUT/$f" "$OUT/$f"
done
(
  cd "$OUT"
  sha256sum runtime.json provider-runner.py provider-pid.txt provider-ready.json stdout.txt stderr.txt exitcode.txt started_at_utc.txt ended_at_utc.txt snapshot-verify.txt gpu-before.csv gpu-after.csv nvidia-smi-compute-poll.log nvidia-smi-compute-after.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf '\n=== 8. Race-check, commit, and push evidence ===\n'
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
[[ "$REMOTE_NOW" == "$SOURCE_HEAD" ]] || fail 'PR branch moved during CUDA smoke; evidence preserved locally but push aborted'
git add "$OUT"
STAGED="$(git diff --cached --name-only)"
[[ -n "$STAGED" ]] || fail 'no CUDA smoke evidence staged'
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    "$OUT"/*) ;;
    *) fail "unexpected staged path: $path" ;;
  esac
done <<< "$STAGED"
git diff --exit-code "origin/main" -- pyproject.toml uv.lock || fail 'root dependency files changed'
git commit -m 'evidence(timer): add offline CUDA runtime smoke'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved after CUDA smoke commit; push aborted'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote SHA mismatch after CUDA smoke push'

echo
echo '============================================================'
echo 'STATUS=OFFLINE_CUDA_SMOKE_EVIDENCE_PUSHED'
echo "RUN_ID=$RUN_ID"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo "EVIDENCE_PATH=$OUT"
echo "GPU_UUID=$GPU_UUID"
echo "PROVIDER_PID=$PROVIDER_PID"
echo "VRAM_BEFORE_TOTAL_MIB=$VRAM_BEFORE_MIB"
echo "VRAM_PEAK_PROVIDER_MIB=$VRAM_PEAK_PROVIDER_MIB"
echo "VRAM_AFTER_TOTAL_MIB=$VRAM_AFTER_MIB"
echo 'CPU_FALLBACK=false'
echo 'FORMAL_RUNTIME_MATRIX=NOT_EXECUTED'
echo '============================================================'
