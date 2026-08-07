#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT=""
PROVIDER_PYTHON=""
REQUEST_PATH=""
SNAPSHOT_PATH=""
CACHE_ROOT=""
DEVICE="cuda"
RUN_ID="tabpfn-v2-$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_ROOT=""
BUNDLE_ROOT=""
NO_WAIT=0
LICENSE_ACCEPTED=0

usage() {
    cat <<'EOF'
Usage:
  run_tabpfn_ts_v2_target_host_certification.sh \
    --repo-root /absolute/repo \
    --provider-python /absolute/provider/.venv/bin/python \
    --request /absolute/request.json \
    --snapshot /absolute/cache/snapshots/<revision> \
    --repository-cache-root /absolute/cache/models--Prior-Labs--TabPFN-v2-reg \
    --accept-prior-labs-license \
    [--device cuda|cpu] \
    [--run-id ID] \
    [--output-root PATH] \
    [--bundle-root PATH] \
    [--no-wait]
EOF
}

while (($#)); do
    case "$1" in
        --repo-root) REPO_ROOT="$2"; shift 2 ;;
        --provider-python) PROVIDER_PYTHON="$2"; shift 2 ;;
        --request) REQUEST_PATH="$2"; shift 2 ;;
        --snapshot) SNAPSHOT_PATH="$2"; shift 2 ;;
        --repository-cache-root) CACHE_ROOT="$2"; shift 2 ;;
        --device) DEVICE="$2"; shift 2 ;;
        --run-id) RUN_ID="$2"; shift 2 ;;
        --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
        --bundle-root) BUNDLE_ROOT="$2"; shift 2 ;;
        --accept-prior-labs-license) LICENSE_ACCEPTED=1; shift ;;
        --no-wait) NO_WAIT=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for value_name in REPO_ROOT PROVIDER_PYTHON REQUEST_PATH SNAPSHOT_PATH CACHE_ROOT; do
    if [[ -z "${!value_name}" ]]; then
        echo "Missing required argument: $value_name" >&2
        usage >&2
        exit 2
    fi
done
if [[ "$DEVICE" != "cuda" && "$DEVICE" != "cpu" ]]; then
    echo "--device must be cuda or cpu" >&2
    exit 2
fi
if [[ "$LICENSE_ACCEPTED" -ne 1 ]]; then
    echo "--accept-prior-labs-license is required" >&2
    exit 2
fi

for command_name in realpath uv git sha256sum python3 tee; do
    command -v "$command_name" >/dev/null
done
if [[ "$DEVICE" == "cuda" ]]; then
    command -v nvidia-smi >/dev/null
fi

REPO_ROOT="$(realpath "$REPO_ROOT")"
PROVIDER_PYTHON="$(realpath "$PROVIDER_PYTHON")"
REQUEST_PATH="$(realpath "$REQUEST_PATH")"
SNAPSHOT_PATH="$(realpath "$SNAPSHOT_PATH")"
CACHE_ROOT="$(realpath "$CACHE_ROOT")"

resolve_from_repo() {
    local value="$1"
    if [[ "$value" = /* ]]; then
        realpath -m "$value"
    else
        realpath -m "$REPO_ROOT/$value"
    fi
}

OUTPUT_ROOT="$(resolve_from_repo "${OUTPUT_ROOT:-artifacts/tabpfn-ts-v2-runtime}")"
BUNDLE_ROOT="$(
    resolve_from_repo "${BUNDLE_ROOT:-artifacts/tabpfn-ts-v2-runtime-bundles}"
)"

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null; then
    echo "BLOCKED: repo-root is not a Git worktree" >&2
    exit 3
fi
if ! git -C "$REPO_ROOT" diff --quiet; then
    echo "BLOCKED: tracked working-tree changes are present" >&2
    exit 3
fi
if ! git -C "$REPO_ROOT" diff --cached --quiet; then
    echo "BLOCKED: staged changes are present" >&2
    exit 3
fi
if [[ -n "$(git -C "$REPO_ROOT" ls-files --others --exclude-standard)" ]]; then
    echo "BLOCKED: untracked, non-ignored files are present" >&2
    exit 3
fi

mkdir -p "$OUTPUT_ROOT" "$BUNDLE_ROOT"
CONSOLE_DIR="$OUTPUT_ROOT/$RUN_ID-bootstrap"
mkdir -p "$CONSOLE_DIR"
CONSOLE_LOG="$CONSOLE_DIR/console.log"
HOST_INVENTORY="$CONSOLE_DIR/host-inventory.json"
STATUS_FILE="$CONSOLE_DIR/status.txt"

exec > >(tee "$CONSOLE_LOG") 2>&1

finish() {
    local code=$?
    trap - EXIT
    printf 'EXIT_CODE=%s\n' "$code" > "$STATUS_FILE"
    if [[ "$NO_WAIT" -eq 0 && -t 0 ]]; then
        read -r -p "Enterキーで終了します..." _
    fi
    exit "$code"
}
trap finish EXIT

echo "TABPFN_TS_V2_TARGET_HOST_START"
echo "RUN_ID=$RUN_ID"
echo "REPO_ROOT=$REPO_ROOT"
echo "DEVICE=$DEVICE"

test -x "$PROVIDER_PYTHON"
test -f "$REQUEST_PATH"
test -d "$SNAPSHOT_PATH"
test -d "$CACHE_ROOT"
test -f "$REPO_ROOT/pyproject.toml"
test -f "$REPO_ROOT/uv.lock"
test -f "$REPO_ROOT/scripts/certify_tabpfn_ts_v2_runtime.py"
test -f "$REPO_ROOT/scripts/package_tabpfn_ts_v2_runtime_evidence.py"

GIT_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
GIT_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
UV_VERSION="$(uv --version)"
PROVIDER_IMPORT="$($PROVIDER_PYTHON - "$DEVICE" <<'PY'
import json
import sys
from importlib.metadata import version

import numpy
import pandas
import torch
import tabpfn_time_series  # noqa: F401

device = sys.argv[1]
package_version = version("tabpfn-time-series")
if package_version != "1.2.0":
    raise SystemExit(f"tabpfn-time-series version mismatch: {package_version}")
if device == "cuda" and not torch.cuda.is_available():
    raise SystemExit("CUDA requested but provider torch reports cuda_available=false")
print(
    json.dumps(
        {
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "torch": torch.__version__,
            "tabpfn_time_series": package_version,
            "cuda_available": bool(torch.cuda.is_available()),
        },
        sort_keys=True,
    )
)
PY
)"

if [[ "$DEVICE" == "cuda" ]]; then
    NVIDIA_QUERY="uuid,name,memory.total,driver_version"
    NVIDIA_SMI_RAW="$(
        nvidia-smi --query-gpu="$NVIDIA_QUERY" --format=csv,noheader,nounits
    )"
    if [[ -z "$NVIDIA_SMI_RAW" ]]; then
        echo "BLOCKED: nvidia-smi returned no GPUs" >&2
        exit 4
    fi
    NVIDIA_SMI_JSON="$(NVIDIA_SMI_RAW="$NVIDIA_SMI_RAW" python3 - <<'PY'
import json
import os

rows = [line.strip() for line in os.environ["NVIDIA_SMI_RAW"].splitlines() if line.strip()]
print(json.dumps(rows))
PY
)"
else
    NVIDIA_SMI_JSON='[]'
fi

python3 - "$HOST_INVENTORY" "$GIT_HEAD" "$GIT_BRANCH" "$UV_VERSION" \
    "$PROVIDER_IMPORT" "$NVIDIA_SMI_JSON" "$REPO_ROOT" "$REQUEST_PATH" <<'PY'
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

path, head, branch, uv_version, provider_raw, gpu_raw, repo_root, request_path = sys.argv[1:]


def sha256(path_value: str) -> str | None:
    candidate = Path(path_value)
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


payload = {
    "captured_at_utc": datetime.now(UTC).isoformat(),
    "platform": platform.platform(),
    "python": sys.version,
    "git_head": head,
    "git_branch": branch,
    "uv_version": uv_version,
    "provider_environment": json.loads(provider_raw),
    "nvidia_smi_gpus": json.loads(gpu_raw),
    "request_sha256": sha256(request_path),
    "pyproject_sha256": sha256(str(Path(repo_root) / "pyproject.toml")),
    "uv_lock_sha256": sha256(str(Path(repo_root) / "uv.lock")),
}
Path(path).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo "PREFLIGHT=PASS"
echo "GIT_HEAD=$GIT_HEAD"
echo "GIT_BRANCH=$GIT_BRANCH"
echo "PROVIDER_IMPORT=$PROVIDER_IMPORT"

set +e
UV_OFFLINE=1 uv run --frozen --offline python \
    "$REPO_ROOT/scripts/certify_tabpfn_ts_v2_runtime.py" \
    --repo-root "$REPO_ROOT" \
    --provider-python "$PROVIDER_PYTHON" \
    --request "$REQUEST_PATH" \
    --snapshot "$SNAPSHOT_PATH" \
    --repository-cache-root "$CACHE_ROOT" \
    --output-root "$OUTPUT_ROOT" \
    --run-id "$RUN_ID" \
    --device "$DEVICE" \
    --seed 1 \
    --repeats 2 \
    --prediction-tolerance 0
CERTIFIER_EXIT=$?
set -e
if [[ "$CERTIFIER_EXIT" -ne 0 ]]; then
    echo "CERTIFICATION_STATUS=FAIL"
    echo "CERTIFIER_EXIT=$CERTIFIER_EXIT"
    exit "$CERTIFIER_EXIT"
fi

RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
BUNDLE_ZIP="$BUNDLE_ROOT/${RUN_ID}-evidence.zip"
UV_OFFLINE=1 uv run --frozen --offline python \
    "$REPO_ROOT/scripts/package_tabpfn_ts_v2_runtime_evidence.py" \
    --run-dir "$RUN_DIR" \
    --output-zip "$BUNDLE_ZIP" \
    --expected-device "$DEVICE" \
    --host-inventory "$HOST_INVENTORY"

echo "CERTIFICATION_STATUS=PASS"
echo "RUN_DIR=$RUN_DIR"
echo "BUNDLE_ZIP=$BUNDLE_ZIP"
echo "BUNDLE_SHA256_FILE=${BUNDLE_ZIP}.sha256"
echo "TABPFN_TS_V2_TARGET_HOST_COMPLETE"
