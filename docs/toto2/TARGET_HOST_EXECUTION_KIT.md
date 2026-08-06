# Toto 2.0 4M target-host execution kit

Status: `IMPLEMENTED / DEPENDENCY_LIGHT_VERIFIED / TARGET_HOST_EXECUTION_PENDING`.

## Purpose

This layer closes the preparation and verification gaps around the 90-case runtime matrix. It does
not execute on behalf of the target host and does not approve a dependency lock automatically.

## Immutable history export contract

Provide one JSON file per game under a read-only directory:

```text
numbers3.json
numbers4.json
miniloto.json
loto6.json
loto7.json
```

Each file must contain:

```json
{
  "schema_version": 1,
  "game_id": "numbers3",
  "position_columns": ["n1", "n2", "n3"],
  "rows": [
    {
      "draw_no": 1,
      "values": {"n1": 1, "n2": 2, "n3": 3}
    }
  ]
}
```

Formal preparation requires at least 512 rows per game. Draw numbers must be positive, unique,
strictly increasing, and gap-free. Values must be finite integers inside the game domain. MiniLoto,
Loto6, and Loto7 positions must be strictly increasing within each row.

The source files are read only. Their SHA-256 values, row counts, and final draw numbers are written
to `REQUEST_MANIFEST.json`. Every context uses the same final observed draw for its game. No future
actual is read or embedded.

## 1. Prepare the target host

Checkout the exact PR stack head, generate and sync the isolated lock candidate, then run:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export HISTORY_ROOT=/absolute/read-only/history-export
export SNAPSHOT=/absolute/huggingface/snapshot/8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9
export EXPECTED_HEAD=<exact-approved-head-sha>
export WORK_ROOT="$PWD/artifacts/toto2-4m-target-host-preparation/$(date -u +%Y%m%dT%H%M%SZ)"

bash environments/toto2-4m-py312/target-host-certification.sh prepare
```

Preparation fails unless:

- tracked Git files are clean and `HEAD` equals `EXPECTED_HEAD`;
- `uv.lock` and the isolated Python environment exist;
- Python and package versions match the pinned runtime contract;
- the model snapshot revision, file hashes, and model weight size match exactly;
- `nvidia-smi` reports at least one GPU;
- all five history exports pass the immutable data contract;
- exactly 90 request files are generated.

Preparation writes `lock_review.pending.json`. It deliberately has `status=PENDING` and all review
flags false. A human must review dependency sources, hashes, licenses, and transitive dependencies,
then set the existing fields to an approved record. Do not replace the lock hash.

## 2. Execute the matrix

```bash
export SNAPSHOT=/absolute/huggingface/snapshot/8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9
export WORK_ROOT=/absolute/preparation-directory
export LOCK_REVIEW="$WORK_ROOT/lock_review.approved.json"

bash environments/toto2-4m-py312/target-host-certification.sh run
```

The matrix remains fail-closed. A partial run is not certification. Each case requires two distinct
provider processes, exact native replay, and the device evidence required by its CPU or CUDA lane.

## 3. Independently verify the ZIP

```bash
export ARCHIVE=/absolute/matrix-run.zip
export ARCHIVE_SHA256_FILE=/absolute/matrix-run.zip.sha256
export VERIFY_OUTPUT=/absolute/INDEPENDENT_VERIFICATION.json

bash environments/toto2-4m-py312/target-host-certification.sh verify
```

Independent verification checks archive SHA-256, safe paths, deterministic timestamps, the embedded
artifact manifest, all 90 successful cases, all 90 exact replays, 45 CPU cases, 45 CUDA cases, and
GPU PID/UUID/positive-VRAM evidence from both processes of every CUDA case.

## Certification boundary

A verified runtime ZIP does not certify forecast accuracy or lottery-domain suitability. OOF,
Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, and baseline comparisons remain separate later gates.
