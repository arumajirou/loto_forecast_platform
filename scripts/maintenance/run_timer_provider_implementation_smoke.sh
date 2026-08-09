#!/usr/bin/env bash
set -Eeuo pipefail

CTX="${1:-$HOME/loto-maintainer-evidence/pr238-local-20260809T080814Z/LOCAL_CONTEXT.env}"
EXPECTED_LOCK_SHA='5349b4ae2a1c16a0b27b4fe3cf7b77a3d8bd6d0a22329b8b66691c5e3e63efe0'
EXPECTED_CONFIG_SHA='8cf274b6192f6114a0988d1e70277c69531db3611866ae7d4c6f82819c469c7e'
EXPECTED_CPU_SHA='fcdb5aa0f1c306bb1fce7613ad58a5e89601e5b1b46472ff7a74a502b272be83'
EXPECTED_CUDA_SHA='d6b54e3f2bed42d7d81f0cbef200c7bf11ed72506472061d7b6b10a825ec8817'
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

REVIEW="audit/tsfm-runtime/timer-base-84m/remote-code-review.json"
LOCK="environments/timer-base-84m-supported-py310/uv.lock"
ENV_DIR="environments/timer-base-84m-supported-py310"
SNAP="$HOME/.cache/loto/timer-base-84m/snapshots/$REV"
VENV="$HOME/.cache/loto/timer-base-84m/venvs/$EXPECTED_LOCK_SHA"
OUT="$EVIDENCE/timer-provider-implementation-smoke-$(date -u '+%Y%m%dT%H%M%SZ')"
mkdir -p "$OUT"

printf '=== 1. Synchronize exact PR head and verify clean worktree ===\n'
git fetch origin "$HEAD_REF" main
SOURCE_HEAD="$(git rev-parse "origin/$HEAD_REF")"
git merge --ff-only "origin/$HEAD_REF" || fail 'local worktree cannot fast-forward to PR branch'
[[ "$(git rev-parse HEAD)" == "$SOURCE_HEAD" ]] || fail 'local worktree did not reach remote PR head'
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || fail 'worktree is not clean before provider smoke'
echo "SOURCE_HEAD=$SOURCE_HEAD"

printf '\n=== 2. Reverify exact lock/config/review/snapshot prerequisites ===\n'
[[ -x "$VENV/bin/python" ]] || fail 'isolated Timer Python environment missing'
[[ -f "$REVIEW" ]] || fail 'remote-code review missing'
[[ -f "$LOCK" ]] || fail 'isolated lock missing'
[[ -d "$SNAP" ]] || fail 'snapshot missing'
[[ "$(sha256sum "$LOCK" | awk '{print $1}')" == "$EXPECTED_LOCK_SHA" ]] || fail 'isolated lock SHA changed'
CURRENT_CONFIG_SHA="$(PYTHONPATH="$WORKTREE/src" python3 - <<'PY'
from loto.timer_base_84m_campaign.provenance import CONFIG_SHA256
print(CONFIG_SHA256)
PY
)"
[[ "$CURRENT_CONFIG_SHA" == "$EXPECTED_CONFIG_SHA" ]] || fail "CONFIG_SHA256 not exact: $CURRENT_CONFIG_SHA"
echo "PASS CONFIG_SHA256=$CURRENT_CONFIG_SHA"

printf '\n=== 3. Focused root static/unit verification ===\n'
command -v uv >/dev/null 2>&1 || fail 'uv is required for repository verification'
uv run --frozen ruff format --check \
  src/loto/adapters/timer_base_84m/contracts.py \
  src/loto/adapters/timer_base_84m/provider.py \
  src/loto/timer_base_84m_campaign/provenance.py \
  tests/unit/test_timer_base_84m_runtime_provider.py \
  >"$OUT/ruff-format.txt" 2>&1 || { cat "$OUT/ruff-format.txt"; fail 'focused ruff format failed'; }
uv run --frozen ruff check \
  src/loto/adapters/timer_base_84m/contracts.py \
  src/loto/adapters/timer_base_84m/provider.py \
  src/loto/timer_base_84m_campaign/provenance.py \
  tests/unit/test_timer_base_84m_runtime_provider.py \
  >"$OUT/ruff-check.txt" 2>&1 || { cat "$OUT/ruff-check.txt"; fail 'focused ruff check failed'; }
uv run --frozen pytest -q tests/unit/test_timer_base_84m_runtime_provider.py \
  >"$OUT/pytest.txt" 2>&1 || { cat "$OUT/pytest.txt"; fail 'focused provider pytest failed'; }
echo 'PASS FOCUSED_ROOT_VERIFICATION'
cat "$OUT/pytest.txt"

printf '\n=== 4. Certified isolated Python 3.10 provider load/predict smoke ===\n'
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_DATASETS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONHASHSEED=1

set +e
WORKTREE="$WORKTREE" ENV_DIR="$ENV_DIR" REVIEW="$REVIEW" SNAP="$SNAP" \
EXPECTED_CPU_SHA="$EXPECTED_CPU_SHA" EXPECTED_CUDA_SHA="$EXPECTED_CUDA_SHA" \
PYTHONPATH="$WORKTREE/src:$WORKTREE/scripts/maintenance" "$VENV/bin/python" - <<'PY' \
  >"$OUT/provider-smoke.json" 2>"$OUT/provider-smoke.stderr"
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any


def deny_network(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError('NETWORK_ACCESS_BLOCKED_BY_PROVIDER_IMPLEMENTATION_SMOKE')


socket.create_connection = deny_network
socket.socket.connect = deny_network

from loto.adapters.timer_base_84m.provider import TimerBase84MProvider
from loto.timer_base_84m_campaign.chronology import TimeAxis
from loto.timer_base_84m_campaign.geometry import Game
from timer_formal_matrix_runner import build_request

root = Path(os.environ['WORKTREE'])
provider = TimerBase84MProvider(
    environment_dir=root / os.environ['ENV_DIR'],
    review_path=root / os.environ['REVIEW'],
    snapshot_dir=Path(os.environ['SNAP']),
)
load_info = provider.load()
results = {}
for device, expected_sha in (
    ('cpu', os.environ['EXPECTED_CPU_SHA']),
    ('cuda', os.environ['EXPECTED_CUDA_SHA']),
):
    request = build_request(
        game=Game.NUMBERS3,
        axis=TimeAxis.DRAW_SEQUENCE,
        horizon=5,
        layout='position_panel_batched_univariate',
        seed=1,
        device=device,
    )
    response = provider.predict(request)
    if response.status != 'PREDICTED':
        raise SystemExit(f'{device}: response status {response.status}')
    if response.prediction_sha256_f32 != expected_sha:
        raise SystemExit(
            f'{device}: provider prediction SHA mismatch '
            f'{response.prediction_sha256_f32} != {expected_sha}'
        )
    if response.output_shape != (3, 5) or response.finite_check is not True:
        raise SystemExit(f'{device}: invalid output shape/finite result')
    if response.cpu_fallback is not False:
        raise SystemExit(f'{device}: cpu_fallback must be false')
    if device == 'cuda' and (response.gpu_uuid is None or not response.gpu_process_vram_bytes):
        raise SystemExit('cuda: missing provider GPU UUID/VRAM evidence')
    results[device] = response.model_dump(mode='json')
provider.close()
print(json.dumps({'status': 'PASS', 'load': load_info, 'results': results}, indent=2, sort_keys=True))
PY
RC=$?
set -e
[[ "$RC" == '0' ]] || { cat "$OUT/provider-smoke.stderr"; fail "provider implementation smoke failed rc=$RC" "$RC"; }
[[ ! -s "$OUT/provider-smoke.stderr" ]] || { cat "$OUT/provider-smoke.stderr"; fail 'provider smoke emitted stderr'; }
echo 'PASS CERTIFIED_PROVIDER_IMPLEMENTATION_SMOKE'
cat "$OUT/provider-smoke.json"

printf '\n=== 5. Preserve local smoke hashes ===\n'
(
  cd "$OUT"
  sha256sum ruff-format.txt ruff-check.txt pytest.txt provider-smoke.json provider-smoke.stderr > SHA256SUMS
  sha256sum -c SHA256SUMS
)

printf '\n============================================================\n'
echo 'STATUS=PROVIDER_IMPLEMENTATION_SMOKE_PASS'
echo "SOURCE_HEAD=$SOURCE_HEAD"
echo "EVIDENCE_DIR=$OUT"
echo "CPU_PROVIDER_SHA=$EXPECTED_CPU_SHA"
echo "CUDA_PROVIDER_SHA=$EXPECTED_CUDA_SHA"
echo 'CPU_FALLBACK=false'
echo 'HOLDOUT_ACCESSED=false'
echo 'PROSPECTIVE_ACCESSED=false'
echo 'NEXT=REFINALIZE_FORMAL_MATRIX_AND_REPLAY'
echo '============================================================'
