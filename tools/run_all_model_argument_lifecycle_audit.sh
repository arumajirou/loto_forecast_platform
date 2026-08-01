#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${PROFILE:-quick}"
MODELS="${MODELS:-all}"
DEVICE="${DEVICE:-cpu}"
PRECISION="${PRECISION:-32}"
TIMEOUT="${TIMEOUT:-300}"
AVAILABLE_ONLY="${AVAILABLE_ONLY:-1}"
CATALOG_SOURCE="${CATALOG_SOURCE:-merged}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
OUT="${OUT:-$ROOT/runs/all-model-argument-audit-$RUN_ID}"

mkdir -p "$OUT/matrix" "$OUT/runtime"
AVAILABLE_FLAG=()
if [[ "$AVAILABLE_ONLY" == "1" ]]; then
  AVAILABLE_FLAG=(--available-only)
fi

uv run --no-sync python scripts/build_all_model_argument_audit.py \
  --models "$MODELS" \
  --profile "$PROFILE" \
  "${AVAILABLE_FLAG[@]}" \
  --output-dir "$OUT/matrix"

# The existing lifecycle runner is the execution authority. It performs fit,
# prediction, save/load, reload prediction, retraining, property inspection,
# argument verification and resource evidence collection.
set +e

RUNTIME_ENV=()
if [[ "$DEVICE" == "cpu" ]]; then
  RUNTIME_ENV=(env CUDA_VISIBLE_DEVICES="")
elif [[ "$DEVICE" == "cuda" ]]; then
  RUNTIME_ENV=(env CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}")
fi

"${RUNTIME_ENV[@]}" uv run --no-sync python scripts/all_model_runtime_validation.py \
  --catalog-source "$CATALOG_SOURCE" \
  --models "$MODELS" \
  "${AVAILABLE_FLAG[@]}" \
  --require-fit \
  --require-predict \
  --require-save \
  --require-load \
  --require-retrain \
  --require-property-validation \
  --verify-arguments \
  --timeout "$TIMEOUT" \
  --device "$DEVICE" \
  --precision "$PRECISION" \
  --output "$OUT/runtime"

RUNTIME_RC=$?

set -e

uv run --no-sync python - "$OUT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])

matrix_manifest = json.loads(
    (
        root
        / "matrix"
        / "audit_manifest.json"
    ).read_text(encoding="utf-8")
)

runtime_dirs = sorted(
    (
        path
        for path in root.glob("runtime/runtime-*")
        if path.is_dir()
    ),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

runtime_dir = (
    runtime_dirs[0]
    if runtime_dirs
    else None
)

summary_path = (
    runtime_dir / "run_summary.json"
    if runtime_dir is not None
    else None
)

runtime_summary = None

if (
    summary_path is not None
    and summary_path.is_file()
):
    runtime_summary = json.loads(
        summary_path.read_text(
            encoding="utf-8"
        )
    )

counts = (
    runtime_summary.get("counts", {})
    if isinstance(
        runtime_summary,
        dict,
    )
    else {}
)

accepted_statuses = {
    "PASS",
    "SKIPPED",
    "NOT_APPLICABLE",
    "ZERO_SHOT_PASS",
}

failed_count = sum(
    int(value)
    for key, value in counts.items()
    if str(key).upper()
    not in accepted_statuses
)

if runtime_dir is None:
    final_status = (
        "RUNTIME_OUTPUT_NOT_FOUND"
    )
elif runtime_summary is None:
    final_status = (
        "RUNTIME_SUMMARY_NOT_FOUND"
    )
elif failed_count:
    final_status = (
        "COMPLETED_WITH_FAILURES"
    )
else:
    final_status = "PASS"

result = {
    "schema_version": "1.0",
    "matrix": matrix_manifest,
    "runtime_summary": runtime_summary,
    "runtime_output": (
        None
        if runtime_dir is None
        else str(runtime_dir)
    ),
    "status": final_status,
}

(root / "final_audit_manifest.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False))
PY

echo "audit=$OUT"
echo "runtime_exit_code=$RUNTIME_RC"

exit "$RUNTIME_RC"
