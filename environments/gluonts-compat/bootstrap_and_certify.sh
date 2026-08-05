#!/usr/bin/env bash
set -Eeuo pipefail

LANE="compat"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="${RUN_ID:-gluonts-p4-${LANE}-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/${RUN_ID}}"

command -v uv >/dev/null 2>&1 || {
  echo "BLOCKED: uv is required" >&2
  exit 2
}

mkdir -p "${OUT}"

uv lock --project "${ROOT}"
uv sync --project "${ROOT}" --frozen

uv run --project "${ROOT}" python -m loto_gluonts_provider --identity \
  > "${OUT}/identity.json"

python - "${LANE}" "${RUN_ID}" "${OUT}/request.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

lane, run_id, destination = sys.argv[1:]
payload = {
    "schema_version": 1,
    "request_id": f"{run_id}-deepar-cpu",
    "run_id": run_id,
    "lane": lane,
    "operation": "runtime_certify",
    "model_class": "DeepAREstimator",
    "prediction_length": 1,
    "context_length": 8,
    "seed": 1,
    "device": "cpu",
    "arguments": {"run_deepar_cpu_smoke": True},
    "resource_policy": {
        "outer_workers": 8,
        "max_gpu_jobs": 1,
        "threads_per_job": 1,
    },
}
Path(destination).write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY

set +e
uv run --project "${ROOT}" python -m loto_gluonts_provider \
  --request "${OUT}/request.json" \
  --response "${OUT}/response.json" \
  > "${OUT}/provider.stdout.log" \
  2> "${OUT}/provider.stderr.log"
PROVIDER_RC=$?
set -e

python - "${ROOT}" "${OUT}" "${PROVIDER_RC}" <<'PY'
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
provider_rc = int(sys.argv[3])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def label(path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

response_path = out / "response.json"
if not response_path.exists():
    raise SystemExit("FAILED: provider did not write response.json")
response = json.loads(response_path.read_text(encoding="utf-8"))
metadata = response.get("metadata", {})
smoke = metadata.get("deep_ar_cpu_smoke", {})
verified = (
    provider_rc == 0
    and response.get("status") == "PARTIALLY_VERIFIED"
    and metadata.get("fit_predict_certified") is True
    and metadata.get("device_certified") is True
    and smoke.get("outcome") == "VERIFIED"
)

files = [
    root / "pyproject.toml",
    root / "uv.lock",
    out / "identity.json",
    out / "request.json",
    out / "response.json",
    out / "provider.stdout.log",
    out / "provider.stderr.log",
]
manifest = {
    "schema_version": 1,
    "status": "VERIFIED" if verified else "FAILED",
    "provider_return_code": provider_rc,
    "python": platform.python_version(),
    "python_executable": sys.executable,
    "versions": {
        "gluonts": version("gluonts"),
        "torch": version("torch"),
        "lightning": version("lightning"),
        "pytorch_lightning": version("pytorch-lightning"),
    },
    "sha256": {label(path): sha256(path) for path in files},
}
(out / "environment_provenance.json").write_text(
    json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
if not verified:
    raise SystemExit("FAILED: DeepAR CPU smoke did not satisfy the P4 certification contract")
PY

(
  cd "${ROOT}"
  sha256sum \
    pyproject.toml \
    uv.lock \
    "${OUT}/identity.json" \
    "${OUT}/request.json" \
    "${OUT}/response.json" \
    "${OUT}/provider.stdout.log" \
    "${OUT}/provider.stderr.log" \
    "${OUT}/environment_provenance.json" \
    > "${OUT}/SHA256SUMS"
)

echo "P4_GLUONTS_DEEPAR_CPU=VERIFIED"
echo "LANE=${LANE}"
echo "RUN_ID=${RUN_ID}"
echo "ARTIFACT_DIR=${OUT}"
