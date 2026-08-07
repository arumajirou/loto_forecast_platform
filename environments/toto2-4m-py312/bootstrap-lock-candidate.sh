#!/usr/bin/env bash
set -Eeuo pipefail

ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ENV_DIR/../.." && pwd)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$REPO_ROOT/artifacts/toto2-4m-lock-candidate/$RUN_ID"
LOG="$OUT_DIR/bootstrap.log"

mkdir -p "$OUT_DIR"
exec > >(tee "$LOG") 2>&1

on_error() {
  local exit_code=$?
  printf 'LOCK_CANDIDATE_STATUS=FAILED\n'
  printf 'EXIT_CODE=%s\n' "$exit_code"
  printf 'OUT_DIR=%s\n' "$OUT_DIR"
  exit "$exit_code"
}
trap on_error ERR

command -v uv >/dev/null
command -v python3.12 >/dev/null

printf 'LOCK_CANDIDATE_STATUS=RUNNING\n'
printf 'RUN_ID=%s\n' "$RUN_ID"
printf 'ENV_DIR=%s\n' "$ENV_DIR"
printf 'OUT_DIR=%s\n' "$OUT_DIR"

uv --version | tee "$OUT_DIR/uv-version.txt"
python3.12 --version | tee "$OUT_DIR/python-version.txt"

uv lock --project "$ENV_DIR" --python python3.12
uv sync --project "$ENV_DIR" --python python3.12
uv tree --project "$ENV_DIR" --frozen > "$OUT_DIR/uv-tree.txt"
uv export \
  --project "$ENV_DIR" \
  --frozen \
  --format requirements-txt \
  --no-emit-project \
  --output-file "$OUT_DIR/requirements-frozen.txt"

uv run --project "$ENV_DIR" --frozen python - <<'PY'
from __future__ import annotations

import importlib.metadata
import json
import platform

import torch

payload = {
    "python_version": platform.python_version(),
    "torch_version": torch.__version__,
    "torch_cuda_version": torch.version.cuda,
    "toto_2_version": importlib.metadata.version("toto-2"),
    "toto_models_version": importlib.metadata.version("toto-models"),
}
print(json.dumps(payload, indent=2, sort_keys=True))
PY

sha256sum "$ENV_DIR/pyproject.toml" "$ENV_DIR/uv.lock" > "$OUT_DIR/SHA256SUMS"
sha256sum -c "$OUT_DIR/SHA256SUMS"

printf 'LOCK_CANDIDATE_STATUS=PASS\n'
printf 'UV_LOCK=%s\n' "$ENV_DIR/uv.lock"
printf 'OUT_DIR=%s\n' "$OUT_DIR"
printf 'REVIEW_REQUIRED=true\n'
printf 'COMMIT_ALLOWED=false\n'
