#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/e/env/ts/loto_forecast_platform}"
CONFIG="${CONFIG:-${ROOT}/configs/auto_campaign/campaign.yaml}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)}"
GROUP="${GROUP:-${ROOT}/artifacts/miniloto-all-auto/campaign-${RUN_ID}}"

mkdir -p "${GROUP}"
printf '%s\n' "${GROUP}" > "${ROOT}/artifacts/miniloto-all-auto/LATEST-campaign"

run_stage() {
  local stage="$1"
  local output="$2"
  shift 2
  uv run loto-auto-campaign \
    --project-root "${ROOT}" \
    --config "${CONFIG}" \
    run --stage "${stage}" --output "${output}" "$@"
  uv run loto-auto-campaign \
    --project-root "${ROOT}" \
    --config "${CONFIG}" \
    verify --run "${output}"
}

uv run loto-auto-campaign \
  --project-root "${ROOT}" \
  --config "${CONFIG}" \
  inventory --output "${GROUP}/p0-inventory"

uv run loto-auto-campaign \
  --project-root "${ROOT}" \
  --config "${CONFIG}" \
  plan --output "${GROUP}/plan"

run_stage smoke "${GROUP}/p1-smoke"
run_stage api-coverage "${GROUP}/p2-api-coverage"
run_stage coverage "${GROUP}/p2-model-config-coverage"
run_stage hpo "${GROUP}/p3-hpo"
run_stage validate-trials "${GROUP}/p3-validation-replay" \
  --source-run "${GROUP}/p3-hpo"

uv run python \
  scripts/experiments/prepare_all_neuralforecast_auto_accuracy_promotion.py \
  --validation-run "${GROUP}/p3-validation-replay" \
  --output "${GROUP}/p3-accuracy-promotion" \
  --config "${ROOT}/configs/auto_campaign/accuracy.yaml"
(
  cd "${GROUP}/p3-accuracy-promotion"
  sha256sum -c SHA256SUMS
)
uv run loto-auto-campaign \
  --project-root "${ROOT}" \
  --config "${CONFIG}" \
  verify --run "${GROUP}/p3-validation-replay"

run_stage oof "${GROUP}/p4-oof" \
  --source-run "${GROUP}/p3-validation-replay"

uv run python \
  scripts/experiments/fit_all_neuralforecast_auto_accuracy_policy.py \
  --validation-run "${GROUP}/p3-validation-replay" \
  --oof-run "${GROUP}/p4-oof" \
  --output "${GROUP}/p4-accuracy-policy" \
  --config "${ROOT}/configs/auto_campaign/accuracy.yaml"
(
  cd "${GROUP}/p4-accuracy-policy"
  sha256sum -c SHA256SUMS
)
uv run loto-auto-campaign \
  --project-root "${ROOT}" \
  --config "${CONFIG}" \
  verify --run "${GROUP}/p4-oof"

run_stage holdout "${GROUP}/p5-holdout" \
  --source-run "${GROUP}/p4-oof"
uv run python \
  scripts/experiments/apply_all_neuralforecast_auto_accuracy_policy.py \
  --run "${GROUP}/p5-holdout" \
  --policy "${GROUP}/p4-accuracy-policy/accuracy_policy.json" \
  --output "${GROUP}/p5-accuracy-ensemble" \
  --config "${ROOT}/configs/auto_campaign/accuracy.yaml"
(
  cd "${GROUP}/p5-accuracy-ensemble"
  sha256sum -c SHA256SUMS
)

run_stage prospective "${GROUP}/p6-prospective" \
  --source-run "${GROUP}/p4-oof"
uv run python \
  scripts/experiments/apply_all_neuralforecast_auto_accuracy_policy.py \
  --run "${GROUP}/p6-prospective" \
  --policy "${GROUP}/p4-accuracy-policy/accuracy_policy.json" \
  --output "${GROUP}/p6-accuracy-prospective" \
  --config "${ROOT}/configs/auto_campaign/accuracy.yaml"
(
  cd "${GROUP}/p6-accuracy-prospective"
  sha256sum -c SHA256SUMS
)

uv run python - "${GROUP}" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path(sys.argv[1]).resolve()
stages = {}
for manifest in sorted(root.glob("*/manifest.json")):
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    stages[manifest.parent.name] = {
        "status": payload.get("status"),
        "stage": payload.get("stage"),
        "api_coverage_status": payload.get("api_coverage_status"),
        "manifest": str(manifest.relative_to(root)),
    }
local_pass = all(item.get("status") == "PASS" for item in stages.values())
api_partial = any(
    item.get("api_coverage_status") == "PARTIAL_API_COVERAGE"
    for item in stages.values()
)
manifest = {
    "schema_version": "all-auto-campaign-group-v1",
    "created_at": datetime.now(UTC).isoformat(),
    "local_campaign_status": "PASS" if local_pass else "PARTIAL",
    "formal_all_api_coverage": not api_partial,
    "status": (
        "PARTIAL_API_COVERAGE"
        if local_pass and api_partial
        else "PASS"
        if local_pass
        else "PARTIAL"
    ),
    "stages": stages,
}
(root / "CAMPAIGN_MANIFEST.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
lines = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.name == "SHA256SUMS":
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
(root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
PY

echo "LOCAL_ALL_AUTO_CAMPAIGN_FINISHED=${GROUP}"
