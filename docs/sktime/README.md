# sktime forecasting provider

## Status

```text
IMPLEMENTATION=PROPOSED_P0_COMMITTED
TARGET_RUNTIME=sktime==1.0.1
DEFAULT_PROJECT_DEPENDENCIES=UNCHANGED
ROOT_UV_LOCK=UNCHANGED
COMMON_WORKER=UNCHANGED
COMMON_CATALOG=UNCHANGED
GITHUB_WORKFLOW=UNCHANGED
REAL_RUNTIME=EXECUTION_PENDING
```

This directory documents the first isolated sktime integration increment. It is a
provider contract and runtime-certification foundation, not a claim that all public
forecasters can already fit the project data.

## Why the runtime is isolated

The root project declares `sktime>=0.37` only in the `frameworks` extra. Installing the
complete `sktime[forecasting]` dependency set into the root environment may conflict with
provider-specific versions, including StatsForecast. The P0 lane therefore pins core
`sktime==1.0.1` under `environments/sktime-core-py313` and does not modify the root lock.

## P0 scope

The implementation provides:

- strict Pydantic request and response schemas;
- an explicit CPU-only `core-py313` environment lane;
- exact runtime version verification;
- dynamic forecaster discovery through
  `sktime.registry.all_estimators("forecaster")`;
- constructor signatures and selected class-level tags;
- computed discovery and dependency-state counts;
- `NaiveForecaster` fit and relative-horizon prediction;
- finite value, shape, and prediction-index validation;
- save to ZIP, load, and exact re-prediction validation;
- atomic JSON and CSV evidence;
- `ARTIFACT_MANIFEST.json` and portable `SHA256SUMS`;
- failure responses that do not relabel missing runtime evidence as success.

## Environment resolution

The isolated manifest is intentionally committed without a generated `uv.lock`. Resolve
and review the lock on a host with the intended Python and package registry:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
uv lock --project environments/sktime-core-py313
```

A resolved lock is required before formal runtime certification. Merely resolving or
listing a package is not runtime success.

## Run dynamic inventory

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
REQUEST="/tmp/sktime-inventory-${RUN_ID}.json"
OUTPUT="artifacts/sktime/inventory-${RUN_ID}"
LOG="artifacts/sktime/inventory-${RUN_ID}.log"

python - "configs/sktime_campaign/inventory.json" "$REQUEST" "$OUTPUT" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
output = sys.argv[3]
payload = json.loads(source.read_text(encoding="utf-8"))
payload["output_dir"] = output
target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

set -o pipefail
PYTHONPATH=src uv run \
  --project environments/sktime-core-py313 \
  python scripts/run_sktime_provider.py \
  --request "$REQUEST" \
  2>&1 | tee "$LOG"
STATUS="${PIPESTATUS[0]}"
printf '%s\n' "$STATUS" > "${LOG}.exit_code"
printf 'exit_code=%s\n' "$STATUS"
printf 'Press Enter to close.\n'
read -r _
exit "$STATUS"
```

The discovered count must come from the installed runtime. It must not be copied from a
document or manually maintained list.

## Run the NaiveForecaster certification smoke

Use the same command pattern with `configs/sktime_campaign/naive_smoke.json`. A PASS
requires all of the following:

```text
installed version == 1.0.1
fit completed
prediction shape matches fh
prediction index matches the relative RangeIndex horizon
all predictions are finite
ZIP model artifact is non-empty
load_from_path completed
post-load prediction shape and index match
post-load predictions exactly equal pre-save predictions
cpu_fallback=false
SHA256SUMS verifies
```

## Artifacts

Inventory operation:

```text
FORECASTER_INVENTORY.json
FORECASTER_INVENTORY.csv
INVENTORY_SUMMARY.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Naive smoke operation:

```text
naive_forecaster.zip
NAIVE_SMOKE.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

## State vocabulary

Provider responses use:

- `PASS`: the requested operation and all P0 validations completed;
- `PARTIAL`: reserved for later multi-estimator campaigns with incomplete evidence;
- `FAILED`: the runtime was present, but the contract or operation failed;
- `UNAVAILABLE`: sktime or a required runtime import was unavailable.

Inventory rows keep separate states for discovery, import, construction, fit, prediction,
and save/load. `DISCOVERED` or `IMPORTABLE` must never be presented as runtime-verified.

## Certification boundary

This P0 increment does not claim:

- an exact total forecaster count on the target host;
- construction or execution of every discovered forecaster;
- optional dependency installation;
- probabilistic, interval, quantile, hierarchical, panel, or exogenous execution;
- chronological CV, OOF, HPO, Holdout, or Prospective results;
- Hit@±1 improvement;
- MLflow or PostgreSQL persistence;
- GPU support;
- integration into the common worker or common model catalog;
- repository-wide test or GitHub Actions success.

## Next increments

1. Resolve and review the isolated `uv.lock`.
2. Execute inventory and Naive smoke on the target host.
3. Add instance-level tag and constructor-state certification.
4. Add lightweight P0 forecasters and chronological evaluation.
5. Add reduction, pipeline, ensemble, probabilistic, and online tracks separately.
6. Integrate into shared orchestration only after the provider contract is verified.
