#!/usr/bin/env bash
set -Eeuo pipefail

LANE="compat"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
RUN_ID="${RUN_ID:-gluonts-p5-${LANE}-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="${1:-${ROOT}/artifacts/${RUN_ID}}"
PROVIDER_ARTIFACT_ROOT="${OUT}/provider-artifacts"
PREDICTOR_ARTIFACT_DIR="${OUT}/predictor"

command -v uv >/dev/null 2>&1 || {
  echo "BLOCKED: uv is required" >&2
  exit 2
}

mkdir -p "${OUT}"

uv lock --project "${ROOT}"
uv sync --project "${ROOT}" --frozen

uv run --project "${ROOT}" python -m loto_gluonts_provider --identity \
  > "${OUT}/identity.json"

set +e
PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
  uv run --project "${ROOT}" python \
  -m loto.adapters.gluonts.p5_cli \
  --lane "${LANE}" \
  --run-id "${RUN_ID}" \
  --artifact-root "${PROVIDER_ARTIFACT_ROOT}" \
  --predictor-artifact-dir "${PREDICTOR_ARTIFACT_DIR}" \
  > "${OUT}/p5-lifecycle.stdout.log" \
  2> "${OUT}/p5-lifecycle.stderr.log"
LIFECYCLE_RC=$?
set -e

uv run --project "${ROOT}" python - \
  "${ROOT}" "${OUT}" "${LIFECYCLE_RC}" "${LANE}" "${RUN_ID}" <<'PY'
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
lifecycle_rc = int(sys.argv[3])
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


stdout_path = out / "p5-lifecycle.stdout.log"
lines = [line for line in stdout_path.read_text("utf-8").splitlines() if line.strip()]
summary = json.loads(lines[-1]) if lines else {}
verified = (
    lifecycle_rc == 0
    and summary.get("outcome") == "VERIFIED"
    and summary.get("fit_process_id") is not None
    and summary.get("load_process_id") is not None
    and summary["fit_process_id"] != summary["load_process_id"]
)
files = sorted(
    path
    for path in out.rglob("*")
    if path.is_file()
    and path.name not in {"environment_provenance.json", "SHA256SUMS"}
)
manifest = {
    "schema_version": 1,
    "phase": "P5_PREDICTOR_LIFECYCLE",
    "status": "VERIFIED" if verified else "FAILED",
    "lane": lane,
    "run_id": run_id,
    "lifecycle_return_code": lifecycle_rc,
    "python": platform.python_version(),
    "python_executable": sys.executable,
    "versions": {
        "gluonts": version("gluonts"),
        "torch": version("torch"),
        "lightning": version("lightning"),
        "pytorch_lightning": version("pytorch-lightning"),
        "pydantic": version("pydantic"),
    },
    "lifecycle_summary": summary,
    "sha256": {
        str(path.relative_to(out)): sha256(path)
        for path in files
    },
}
destination = out / "environment_provenance.json"
content = (
    json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
).encode("utf-8")
descriptor, temporary_name = tempfile.mkstemp(
    prefix=f".{destination.name}.",
    dir=destination.parent,
)
temporary = Path(temporary_name)
try:
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
finally:
    temporary.unlink(missing_ok=True)

if not verified:
    raise SystemExit(
        "FAILED: Predictor serialize/restart/reload certification did not pass"
    )
PY
PROVENANCE_RC=$?

(
  cd "${OUT}"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    > SHA256SUMS
)

if (( LIFECYCLE_RC != 0 || PROVENANCE_RC != 0 )); then
  echo "P5_GLUONTS_PREDICTOR_LIFECYCLE=FAILED" >&2
  echo "LANE=${LANE}" >&2
  echo "RUN_ID=${RUN_ID}" >&2
  echo "ARTIFACT_DIR=${OUT}" >&2
  exit 1
fi

echo "P5_GLUONTS_PREDICTOR_LIFECYCLE=VERIFIED"
echo "LANE=${LANE}"
echo "RUN_ID=${RUN_ID}"
echo "ARTIFACT_DIR=${OUT}"
