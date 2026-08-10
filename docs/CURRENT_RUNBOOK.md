# Current Runbook

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:20+09:00
audited_main_sha: cc7ec5473730cfb18100bdfbb5228cf65e571b32
```

## Purpose

Use this runbook for repository maintenance and for the unified development-only evaluation campaign. It does not authorize Holdout, Prospective or promotion.

## Repository preflight

Always start from live state rather than copied status prose.

```bash
git fetch origin
git switch main
git pull --ff-only
uv lock --check
```

For GitHub PR work, record:

- live main SHA;
- PR base/head SHA;
- draft/mergeable state;
- changed files;
- head-vs-main ahead/behind relation;
- exact-head CI runs;
- unresolved review threads.

When two dependency PRs modify `pyproject.toml`/`uv.lock`, merge them serially. Rebase or recreate the remaining Dependabot PR after each merge and re-run verification. Use expected-head guards on merge.

## Environment verification

Recommended repository checks:

```bash
uv sync --locked --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

Run focused tests/smokes first while changing code; reserve the full suite for the completed implementation or merge gate.

## Unified campaign plan-only check

```bash
uv run loto3 campaign --output unused --plan-only
```

Expected behavior:

- enumerates the requested broad catalog × game matrix;
- does not execute models;
- does not open Holdout or Prospective.

## Input data contract for a real development campaign

Provide one canonical CSV per game:

```text
mini.csv
loto6.csv
loto7.csv
bingo5.csv
numbers3.csv
numbers4.csv
```

Each file must contain `draw_no` plus the exact target columns defined by `loto.game.geometry`.

Before execution:

1. preserve the raw source as an immutable snapshot;
2. compute and record a data hash;
3. verify chronological ordering;
4. reject duplicate draw identifiers;
5. reject missing or non-finite target values;
6. verify game-domain legality;
7. ensure no future-derived feature is present;
8. select a new output directory that does not already exist.

## Development campaign execution

```bash
RUN_ID="unified-$(date +%Y%m%d-%H%M%S)"
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output "artifacts/unified-campaign/${RUN_ID}"
```

Do not reuse a prior output directory. The campaign is intentionally single-use to protect evidence.

## Required evaluation interpretation

Primary metric:

```text
Hit@±1 / hit_at_1
```

Also inspect:

- per-position Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE;
- all configured seed results;
- mean/population variance/worst seed and worst value;
- mandatory baseline comparisons.

Mandatory baselines:

```text
random
fixed
mean
median
last
frequency
statistical_ar1
```

A model should not be selected from its best seed only.

## Result-status interpretation

A complete result matrix does not imply universal success.

Expected fail-visible states include:

```text
FAILED
UNAVAILABLE
NOT_ROUTABLE
UNSUPPORTED_GAME
PARTIAL_SEEDS
NON_STANDALONE_METHOD
```

Do not drop those rows from coverage reporting.

## Prediction lock verification

For each evaluated game/candidate/seed, verify the prediction lock exists and records `actuals_known=false`. Retain its SHA-256 and timestamp evidence. Scoring must occur only after the prediction artifact is persisted and sealed.

Check final artifacts including:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/
prediction_locks/
SHA256SUMS
```

## Runtime certification checks

When a row is expected to execute a real model, verify more than catalog availability:

- dependency import;
- model load;
- valid input construction;
- inference completion;
- expected output shape;
- finite values;
- requested/observed device;
- GPU PID and VRAM when CUDA is claimed;
- explicit CPU fallback behavior;
- reload inference when certification requires persistence.

Do not translate `registered`, `available` or `dependency installed` into `runtime certified`.

## Holdout and Prospective gate

Default state is closed.

Do not open Holdout unless the approved development/OOF protocol, seed aggregation, baseline comparisons, leakage checks and prediction-lock evidence are complete and reviewed.

Do not open Prospective merely because Holdout is available. Prospective predictions must be sealed before future actuals exist.

## Current scientific workstreams

- GitHub #239: Timer Base 84M leakage-safe OOF.
- GitHub #118: Timer-S1 immutable runtime/certification PR-B.

Check their live state before acting.

## Incident / failure handling

If a model or provider fails:

1. preserve the failure row and logs;
2. classify dependency, routing, unsupported-game, model-build, inference, non-finite, shape, device or timeout causes;
3. do not mutate old prediction/evidence artifacts;
4. fix on a new branch/run;
5. rerun focused tests and smoke before full CI;
6. create a new Run ID/output directory.

If GitHub CI is queued, report it as queued. If it is cancelled, report cancelled. Neither is PASS.
