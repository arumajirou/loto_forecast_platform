#!/usr/bin/env bash
set -Eeuo pipefail

LANE="compat"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p6-${LANE}-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/${RUN_ID}}"

command -v uv >/dev/null 2>&1 || {
  echo "BLOCKED: uv is required" >&2
  exit 2
}

mkdir -p "${OUT}"
uv lock --project "${ROOT}"
uv sync --project "${ROOT}" --frozen

PROVIDER_COMMAND="uv run --project ${ROOT} python -m loto_gluonts_provider.p6_provider"
set +e
PYTHONPATH="${REPO_ROOT}/src" \
uv run --project "${ROOT}" python -m loto.adapters.gluonts.p6_campaign_cli \
  --run-id "${RUN_ID}" \
  --lane "${LANE}" \
  --provider-command "${PROVIDER_COMMAND}" \
  --artifact-root "${OUT}" \
  --workers 8 \
  --timeout-seconds 600 \
  > "${OUT}/p6_campaign.stdout.log" \
  2> "${OUT}/p6_campaign.stderr.log"
CAMPAIGN_RC=$?
set -e

python - "${ROOT}" "${REPO_ROOT}" "${OUT}" "${LANE}" "${RUN_ID}" <<'PY'
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

root = Path(sys.argv[1])
repo_root = Path(sys.argv[2])
out = Path(sys.argv[3])
lane = sys.argv[4]
run_id = sys.argv[5]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None

result_path = out / "p6_campaign_result.json"
manifest_path = out / "p6_campaign_manifest.json"
result = json.loads(result_path.read_text("utf-8"))
provenance = {
    "schema_version": 1,
    "phase": "P6_ALL_NINE_ESTIMATORS",
    "run_id": run_id,
    "lane": lane,
    "status": result["status"],
    "workers": result["workers"],
    "python": platform.python_version(),
    "python_executable": sys.executable,
    "versions": {
        "gluonts": version("gluonts"),
        "torch": version("torch"),
        "lightning": version("lightning"),
        "pytorch_lightning": version("pytorch-lightning"),
    },
    "sha256": {
        "lane_pyproject": sha256(root / "pyproject.toml"),
        "lane_uv_lock": sha256(root / "uv.lock"),
        "campaign_result": sha256(result_path),
        "campaign_manifest": sha256(manifest_path),
        "registry_source": sha256(
            repo_root / "src/loto/adapters/gluonts/p6_registry.py"
        ),
        "contract_source": sha256(
            repo_root / "src/loto/adapters/gluonts/p6_contract.py"
        ),
    },
}
(out / "p6_environment_provenance.json").write_text(
    json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)
PY

find "${OUT}" -type f ! -name P6_SHA256SUMS -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > "${OUT}/P6_SHA256SUMS"

if [[ "${CAMPAIGN_RC}" -ne 0 ]]; then
  echo "P6_GLUONTS_ALL_MODELS=FAILED"
  echo "CAMPAIGN_RC=${CAMPAIGN_RC}"
  exit "${CAMPAIGN_RC}"
fi

echo "P6_GLUONTS_ALL_MODELS=VERIFIED"
echo "LANE=${LANE}"
echo "RUN_ID=${RUN_ID}"
echo "ARTIFACT_DIR=${OUT}"
