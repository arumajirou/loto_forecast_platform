# Current Runbook

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T20:23+09:00
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

## 1. Purpose

Use this runbook to select model/library execution paths, perform development evaluation, inspect runtime evidence, plan statistical detectability and preserve scientific gates. It does not authorize Holdout, Prospective or promotion by itself.

## 2. Repository preflight

```bash
cd /absolute/path/to/loto_forecast_platform || exit 1
git fetch origin
git status --short --branch
git branch --show-current
git rev-parse HEAD
git remote -v
uv lock --check
```

Before a PR merge re-fetch main/head/base, mergeability, changed files, ahead/behind, CI and unresolved threads. Use expected-head guarded merge. Queued/cancelled Actions are not PASS.

## 3. Environment setup

Repository development:

```bash
uv sync --locked --extra dev
uv run loto-build-info
uv run loto system doctor
```

Heavy shared libraries:

```bash
uv sync --locked --extra full --extra frameworks --extra tsfm
```

Do not install provider-specific incompatible stacks into root merely for convenience. Use `environments/**` where the provider contract requires isolation.

## 4. Inspect available surfaces

```bash
uv run loto3 games
uv run loto3 catalog --counts
uv run loto models list --format table
uv run loto3 probabilistic catalog-list
uv run loto3 probabilistic backends
```

Interpretation:

```text
broad catalog -> inventory/planning
shared catalog -> normal executable specs
provider campaign -> isolated execution
runtime audit -> exact identity evidence
```

## 5. Inspect one model before using it

```bash
uv run loto models show nf-nhits
```

Check:

- library/task/class;
- required package/extra;
- shared vs provider route;
- game/layout assumptions;
- device/precision requirements;
- exact revision for foundation models;
- existing runtime evidence;
- whether OOF evidence exists separately.

## 6. Unified campaign plan

```bash
uv run loto3 campaign --output unused --plan-only
```

Subset:

```bash
uv run loto3 campaign \
  --output unused \
  --games numbers3,numbers4,loto7 \
  --models logistic,nf-nhits,chronos-2 \
  --plan-only
```

Verify expected pair count and retain non-routable entries instead of filtering them away post hoc.

## 7. Prepare real data

For all six games, input directory uses:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

Before execution:

- freeze immutable snapshot;
- record SHA-256;
- verify draw identity/chronology;
- check missing/duplicate/non-finite data;
- check geometry legality;
- reject future-derived features;
- decide development/Holdout boundary without looking at Holdout results.

## 8. Resource preflight

Measure CPU/RAM/storage/GPU before a long campaign. Record the resolved budget in run config/evidence.

Key campaign controls:

```text
--device
--precision
--max-trials
--parallel-trials
--max-steps
--wall-time-seconds
--gpu-count
--gpu-memory-bytes
```

Do not assume a package supports CUDA because it is installed. Effective device must be measured for runtime certification.

## 9. Run development campaign

```bash
RUN_ID="unified-$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/unified-campaign/${RUN_ID}"

uv run loto3 campaign \
  --input-dir /absolute/path/to/canonical-csv-directory \
  --output "$OUT" \
  --seeds 42,1729,20260730 \
  --folds 5 \
  --test-size 20 \
  --min-train-size 100 \
  --holdout-size 50 \
  --device auto \
  --precision 32
```

Never reuse `OUT` from an older run.

## 10. Inspect campaign results

Required artifacts:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/
prediction_locks/
SHA256SUMS
```

Inspect status counts including:

```text
SUCCEEDED
PARTIAL_SEEDS
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
NON_STANDALONE_METHOD
```

`matrix_complete` is coverage, not universal success.

## 11. Metrics interpretation

Primary: Hit@±1.

Also inspect:

- per-position Hit@±1;
- all-position Hit@±1;
- MAE/MSE/RMSE;
- every seed;
- variance/std;
- worst seed;
- every mandatory baseline.

Geometry rule:

- select hit count = set overlap;
- digit hit count = exact positional matches.

Do not convert Numbers3/4 to unordered sets.

## 12. Mandatory baselines

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

A model has not passed formal comparison if required baseline evidence is missing.

## 13. Prediction-lock audit

For each evaluated game/candidate/seed verify:

```text
actuals_known=false
prediction payload non-empty
SHA-256/timestamp present
lock created before target actual scoring read
```

Do not repair an old evidence directory in place. Use a new Run ID.

## 14. Decoder audit

Probability-bearing candidates should retain:

```text
distribution_identity = row-normalized-slot-binary-probability-v1
decoder objective
post-processing identity
```

Expected family behavior:

```text
digits -> positional WITHIN_TAU/window-mass
select -> legal constrained WITHIN_TAU DP
point-only -> point legalisation, no fake PMF
```

## 15. NeuralForecast AutoModel run

Example:

```bash
uv run loto neuralforecast automodel-run \
  --db-url sqlite:///data/platform.sqlite3 \
  --table normalized_draws \
  --game numbers4 \
  --models nf-auto-dlinear,nf-auto-nhits \
  --backend optuna \
  --num-samples 10 \
  --cpus 8 \
  --gpus 1 \
  --parallel-trials 2 \
  --seed 1 \
  --output artifacts/nf-auto-run
```

For Ray use `--backend ray`. Preserve failed trials and exact search/resource identity.

## 16. Foundation model run preparation

Before a TSFM/provider run:

```bash
uv run loto3 revisions validate \
  --manifest configs/tsfm/verified-revisions.json \
  --require-complete
```

Then verify:

- repo/model/revision;
- local snapshot/artifact hash if required;
- provider class/isolated runner;
- package lock;
- trust-remote-code review where applicable;
- target game/layout/context/horizon;
- requested device.

After execution record actual load/inference/output/device evidence separately from OOF metrics.

## 17. Probabilistic models

```bash
uv run loto3 probabilistic compatibility \
  --model-id <id> \
  --game numbers3 \
  --backend builtin

uv run loto3 probabilistic validate-config --config <config.yaml>
uv run loto3 probabilistic plan --config <config.yaml>
uv run loto3 probabilistic smoke --config <config.yaml>
uv run loto3 probabilistic run --config <config.yaml>
```

Then use `status`, `diagnose`, `compare` on the run directory.

## 18. Theory-aware target planning

Before interpreting a target such as “Hit@±1 90%”, inspect the game-specific theory reference rather than assuming the same meaning for every geometry.

```bash
uv run loto3 theory --game loto7 --tau 1
uv run loto3 theory --game numbers3 --tau 1
```

For new policy code use `TheoryAwareThreshold` semantics:

```text
absolute
excess_vs_iid_null
```

Targets above an IID-null absolute reference require an explicit alternative-hypothesis declaration to pass the guard.

## 19. MDE/power planning before a target window

Use only a `score_sd` fixed from allowed development/pilot evidence or a declared simulation.

Example Python:

```python
from loto.evaluation.power_analysis import PowerPlan, minimum_detectable_effect

plan = PowerPlan(alpha=0.05, target_power=0.80, multiplicity=10)
result = minimum_detectable_effect(500, 0.20, plan=plan)
print(result.model_dump())
```

Use the result to decide whether a planned sample can detect the declared effect size. Do not call it a p-value or realized result.

## 20. Holdout gate

Default: closed.

Only open after reviewed OOF/development evidence establishes:

- immutable protocol/data/model identity;
- leakage checks;
- all baselines;
- all seeds;
- prediction sealing;
- adequate statistical plan;
- explicit authorization.

No retuning on Holdout.

## 21. Prospective gate

Prospective prediction must be sealed before future actual is available/read. Later actual ingestion/scoring is separate.

Multiple windows may be required by promotion policy.

## 22. Promotion eligibility audit

Promotion v2 requires:

- policy game;
- sealed `game_id` on every Holdout/Prospective score window;
- matching game identity;
- theory-resolved absolute target;
- minimum windows/draws;
- stability where required;
- baseline comparison;
- degradation limits.

Even all-pass means:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
```

not automatic promotion.

Verify safety flags remain false for auto promotion/retraining/registry writes.

## 23. Runtime certification

For a runtime claim verify applicable:

```text
import
load
input
inference
shape
finite values
requested/effective device
GPU PID/VRAM/utilization
CPU fallback
save/reload
cleanup
```

Do not infer from catalog availability.

## 24. Final repository validation

After focused tests pass and changes are complete:

```bash
uv sync --locked --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

For documentation-only changes, code regression CI remains valuable as a final repository gate but should not be run repeatedly during editing.

## 25. Failure handling

Preserve failure status/logs, classify cause, create a new fix/run identity, execute focused verification first, and never mutate old immutable prediction/protocol evidence to make a failed run appear successful.
