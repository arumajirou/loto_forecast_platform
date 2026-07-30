# Loto Overnight Model Matrix v1

This harness executes a bounded, auditable matrix of available models and accepted argument combinations.

## Important

“All possible values of every argument” is mathematically impossible for continuous and unbounded parameters. This harness instead:

- discovers model IDs from `configs/model_catalog.json`
- uses finite representative value sets
- validates every generated config before training
- isolates each run
- continues after errors
- records timeout, CUDA OOM, import/config/data errors
- samples GPU telemetry
- writes CSV, JSON and Markdown summaries

## Install

Copy:

- `overnight_model_matrix.py` → `scripts/overnight_model_matrix.py`
- `run_overnight_model_matrix.sh` → project root

Then:

```bash
chmod +x scripts/overnight_model_matrix.py run_overnight_model_matrix.sh
```

## Dry run

```bash
uv run python scripts/overnight_model_matrix.py \
  --profile overnight \
  --parallel 2 \
  --max-runs 500 \
  --device auto \
  --dry-run
```

Review `matrix.json` before starting.

## Overnight start

For a 16 GB GPU, begin with one GPU training process:

```bash
nohup env \
  PROFILE=overnight \
  PARALLEL=1 \
  MAX_RUNS=500 \
  TIMEOUT=3600 \
  DEVICE=auto \
  ./run_overnight_model_matrix.sh \
  >"/mnt/e/env/ts/logs/overnight-launch-$(date +%Y%m%d-%H%M%S).log" \
  2>&1 &
```

CPU-only safe parallel execution:

```bash
nohup env \
  PROFILE=overnight \
  PARALLEL=4 \
  MAX_RUNS=500 \
  TIMEOUT=3600 \
  DEVICE=cpu \
  ./run_overnight_model_matrix.sh \
  >"/mnt/e/env/ts/logs/overnight-launch-$(date +%Y%m%d-%H%M%S).log" \
  2>&1 &
```

## Morning check

```bash
cd /mnt/e/env/ts/loto_forecast_platform

LATEST="$(find runs/overnight-model-matrix -mindepth 1 -maxdepth 1 -type d \
  -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"

cat "$LATEST/summary.json"
sed -n '1,240p' "$LATEST/REPORT.md"

uv run python - "$LATEST/results.csv" <<'PY'
import sys
import pandas as pd
p = sys.argv[1]
df = pd.read_csv(p)
print(df.groupby(["model_id", "status"]).size().unstack(fill_value=0))
print("\nSlowest runs:")
print(df.nlargest(20, "elapsed_seconds")[["model_id","status","elapsed_seconds","run_name"]].to_string(index=False))
PY
```

## Profiles

- `smoke`: 4 combinations per model
- `overnight`: up to 36 combinations per model
- `exhaustive`: all configured finite combinations, still bounded by `--max-runs`

## Outputs

```text
runs/overnight-model-matrix/<timestamp>/
├── matrix.json
├── configs/
├── logs/
├── runs/
├── gpu_samples.csv
├── results.csv
├── summary.json
└── REPORT.md
```
