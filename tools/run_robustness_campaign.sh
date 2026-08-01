#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FOLDS="${FOLDS:-100}"
SEEDS="${SEEDS:-42 43 44}"
CAMPAIGN_ID="${CAMPAIGN_ID:-exogenous-v23-$(date +%Y%m%d-%H%M%S)}"
OUT="$ROOT/runs/$CAMPAIGN_ID"
mkdir -p "$OUT"
for seed in $SEEDS; do
  seed_out="$OUT/seed-$seed"
  uv run python scripts/analysis/run_candidate_exog_robustness_v21.py \
    --folds "$FOLDS" --seed "$seed" \
    --models extra-trees lightgbm-classifier \
    --output-dir "$seed_out"
done
python - <<PY
from pathlib import Path
import pandas as pd
root=Path(${OUT@Q})
files=sorted(root.glob('seed-*/ablation_results.csv'))
if not files: raise SystemExit('no campaign outputs')
combined=pd.concat([pd.read_csv(p) for p in files], ignore_index=True)
expected=int(${FOLDS@Q})*len(${SEEDS@Q}.split())*2*12
if len(combined)!=expected: raise SystemExit(f'row mismatch: {len(combined)} != {expected}')
path=root/'combined_results.csv'; combined.to_csv(path,index=False)
print(path)
PY
uv run python scripts/analysis/aggregate_condition_contributions.py \
  --input "$OUT/combined_results.csv" --output-dir "$OUT/analysis"
echo "campaign=$OUT"
