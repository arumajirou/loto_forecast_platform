#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_PACKET_SHA='0d7800ae8b70274b034cc5a37893ae806b21f0bee8da5854a470ffe257491512'
REV='70077a71acce1b4c00d98332fcaabc694255d8e5'

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
ENV_DIR="environments/timer-base-84m-supported-py310"
LOCK="$ENV_DIR/uv.lock"
SNAP="$HOME/.cache/loto/timer-base-84m/snapshots/$REV"
VENV="$HOME/.cache/loto/timer-base-84m/venvs/$EXPECTED_LOCK_SHA"
RUN_ID="timer-cpu-smoke-$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="audit/local-runs/$RUN_ID"
LOCAL_OUT="$EVIDENCE/$RUN_ID"
mkdir -p "$LOCAL_OUT"

printf '=== 1. Synchronize and bind exact source head ===\n'
git fetch origin "$HEAD_REF" main
SOURCE_HEAD="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$SOURCE_HEAD" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before CPU smoke'
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Enforce named-human approval gate ===\n'
[[ -f "$APPROVAL_RECORD" ]] || fail 'HUMAN_APPROVAL.json missing; runtime remains unauthorized' 65
[[ -f "$REMOTE_REVIEW" ]] || fail 'remote-code review missing'
[[ -f "$DEP_REVIEW" ]] || fail 'dependency review missing'
[[ -f "$LOCK" ]] || fail 'isolated lock missing'
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
if approval.get('runtime_certified') is not False:
    raise SystemExit('pre-runtime approval record has unexpected runtime state')
if remote.get('approved') is not True or remote.get('trust_remote_code_allowed') is not True:
    raise SystemExit('remote-code review is not approved')
if dep.get('human_approved') is not True or dep.get('lock_sha256') != os.environ['EXPECTED_LOCK_SHA']:
    raise SystemExit('dependency lock is not human-approved')
print('PASS HUMAN_APPROVAL_GATE reviewer=' + str(approval.get('reviewer')))
PY

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
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$EXPECTED_LOCK_SHA" ]] || fail 'isolated lock changed before runtime'
echo 'PASS SNAPSHOT_AND_LOCK_RECHECK'

printf '\n=== 4. Execute frozen/offline CPU load + deterministic predict smoke ===\n'
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=''
export PYTHONHASHSEED=1
export HF_HOME="$HOME/.cache/loto/timer-base-84m/hf-offline"
mkdir -p "$HF_HOME"

STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
set +e
SNAP="$SNAP" OUT_JSON="$LOCAL_OUT/runtime.json" SOURCE_HEAD="$SOURCE_HEAD" STARTED_AT="$STARTED_AT" \
"$VENV/bin/python" - <<'PY' >"$LOCAL_OUT/stdout.txt" 2>"$LOCAL_OUT/stderr.txt"
from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fail closed if any Python-level network connection is attempted.
def _deny_network(*args, **kwargs):
    raise RuntimeError('NETWORK_ACCESS_BLOCKED_BY_TIMER_CPU_SMOKE')

socket.create_connection = _deny_network
socket.socket.connect = _deny_network

import torch
import transformers
from transformers import AutoModelForCausalLM

snap = Path(os.environ['SNAP']).resolve()
out_json = Path(os.environ['OUT_JSON'])
started_at = os.environ['STARTED_AT']

torch.manual_seed(1)
torch.set_grad_enabled(False)

model = AutoModelForCausalLM.from_pretrained(
    str(snap),
    trust_remote_code=True,
    local_files_only=True,
    torch_dtype=torch.float32,
)
model.eval()
model.to('cpu')

params = list(model.parameters())
buffers = list(model.buffers())
parameter_count = sum(p.numel() for p in params)
finite_parameters = all(bool(torch.isfinite(p).all()) for p in params)
finite_buffers = all(bool(torch.isfinite(b).all()) for b in buffers if b.is_floating_point())
model_device = str(params[0].device) if params else 'cpu'

# Synthetic, deterministic, non-Holdout/non-Prospective smoke input.
x = torch.linspace(-1.0, 1.0, steps=96, dtype=torch.float32).reshape(1, 96)
with torch.inference_mode():
    y = model.generate(x, max_new_tokens=1)

if y.ndim != 2:
    raise RuntimeError(f'unexpected output ndim: {y.ndim}')
if y.shape[0] != 1:
    raise RuntimeError(f'unexpected output batch: {tuple(y.shape)}')
if not bool(torch.isfinite(y).all()):
    raise RuntimeError('non-finite CPU smoke output')

raw = y.detach().cpu().contiguous().numpy().tobytes()
prediction_sha256 = hashlib.sha256(raw).hexdigest()

payload = {
    'schema_version': 'timer-base-84m.offline-cpu-smoke.v1',
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
    'requested_device': 'cpu',
    'effective_device': model_device,
    'cpu_fallback': False,
    'input_shape': list(x.shape),
    'output_shape': list(y.shape),
    'prediction_sha256': prediction_sha256,
    'network_policy': 'HF/Transformers offline + local_files_only + Python socket deny guard',
    'snapshot_path': str(snap),
    'synthetic_input_only': True,
    'holdout_accessed': False,
    'prospective_accessed': False,
}
if not finite_parameters or not finite_buffers:
    raise RuntimeError('non-finite model parameter/buffer detected')
if model_device != 'cpu':
    raise RuntimeError(f'CPU smoke model device mismatch: {model_device}')
out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True))
PY
RC=$?
set -e
ENDED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '%s\n' "$RC" > "$LOCAL_OUT/exitcode.txt"
printf '%s\n' "$STARTED_AT" > "$LOCAL_OUT/started_at_utc.txt"
printf '%s\n' "$ENDED_AT" > "$LOCAL_OUT/ended_at_utc.txt"
[[ "$RC" == '0' ]] || {
  echo '--- stdout ---'; cat "$LOCAL_OUT/stdout.txt" || true
  echo '--- stderr ---'; cat "$LOCAL_OUT/stderr.txt" || true
  fail "offline CPU smoke failed rc=$RC" "$RC"
}
[[ -f "$LOCAL_OUT/runtime.json" ]] || fail 'CPU smoke runtime.json missing after successful process'
echo 'PASS OFFLINE_CPU_SMOKE'
cat "$LOCAL_OUT/runtime.json"

printf '\n=== 5. Promote compact evidence into repository ===\n'
mkdir -p "$OUT"
cp "$LOCAL_OUT/runtime.json" "$OUT/runtime.json"
cp "$LOCAL_OUT/stdout.txt" "$OUT/stdout.txt"
cp "$LOCAL_OUT/stderr.txt" "$OUT/stderr.txt"
cp "$LOCAL_OUT/exitcode.txt" "$OUT/exitcode.txt"
cp "$LOCAL_OUT/started_at_utc.txt" "$OUT/started_at_utc.txt"
cp "$LOCAL_OUT/ended_at_utc.txt" "$OUT/ended_at_utc.txt"
cp "$LOCAL_OUT/snapshot-verify.txt" "$OUT/snapshot-verify.txt"
(
  cd "$OUT"
  sha256sum runtime.json stdout.txt stderr.txt exitcode.txt started_at_utc.txt ended_at_utc.txt snapshot-verify.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf '\n=== 6. Race-check, commit, and push evidence ===\n'
git fetch origin "$HEAD_REF"
REMOTE_NOW="$(git rev-parse "origin/$HEAD_REF")"
[[ "$REMOTE_NOW" == "$SOURCE_HEAD" ]] || fail 'PR branch moved during CPU smoke; evidence preserved locally but push aborted'
git add "$OUT"
STAGED="$(git diff --cached --name-only)"
[[ -n "$STAGED" ]] || fail 'no CPU smoke evidence staged'
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    "$OUT"/*) ;;
    *) fail "unexpected staged path: $path" ;;
  esac
done <<< "$STAGED"
UNSTAGED="$(git diff --name-only)"
UNTRACKED="$(git ls-files --others --exclude-standard)"
[[ -z "$UNSTAGED" ]] || fail 'unexpected unstaged tracked changes before CPU smoke commit'
[[ -z "$UNTRACKED" ]] || fail 'unexpected untracked files before CPU smoke commit'
# No root dependency mutation is permitted.
git diff --exit-code "origin/main" -- pyproject.toml uv.lock || fail 'root dependency files changed'
git commit -m 'evidence(timer): add offline CPU runtime smoke'
LOCAL_NEW_HEAD="$(git rev-parse HEAD)"
git fetch origin "$HEAD_REF"
[[ "$(git rev-parse "origin/$HEAD_REF")" == "$SOURCE_HEAD" ]] || fail 'PR branch moved after CPU smoke commit; push aborted'
git push origin "HEAD:$HEAD_REF"
git fetch origin "$HEAD_REF"
PUSHED_HEAD="$(git rev-parse "origin/$HEAD_REF")"
[[ "$PUSHED_HEAD" == "$LOCAL_NEW_HEAD" ]] || fail 'remote SHA mismatch after CPU smoke push'

echo
echo '============================================================'
echo 'STATUS=OFFLINE_CPU_SMOKE_EVIDENCE_PUSHED'
echo "RUN_ID=$RUN_ID"
echo "PUSHED_HEAD=$PUSHED_HEAD"
echo "EVIDENCE_PATH=$OUT"
echo 'CUDA_INFERENCE=NOT_EXECUTED'
echo 'FORMAL_RUNTIME_MATRIX=NOT_EXECUTED'
echo '============================================================'
