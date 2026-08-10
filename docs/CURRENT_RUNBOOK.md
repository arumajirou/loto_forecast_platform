# Current Runbook

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:59+09:00
audited_main_sha: 8430d9f507ba735bf1df69930e057c974752bfdb
```

## Purpose

Use this runbook for repository maintenance and the unified development-only evaluation campaign. It does not authorize Holdout, Prospective or promotion.

## Repository preflight

Always start from live state:

```bash
git fetch origin
git switch main
git pull --ff-only
uv lock --check
```

For every PR record live main SHA, PR base/head SHA, draft/mergeable state, changed files, ahead/behind relation, exact-head CI, and unresolved review threads. Dependency PRs sharing `pyproject.toml` or `uv.lock` must be merged serially and rebased/recreated after each merge. Use `expected_head_sha`.

Queued, cancelled and failed Actions runs are not PASS.

## Repository validation

During implementation prefer focused tests/smokes. At the final gate:

```bash
uv sync --locked --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

## Unified campaign

Plan only:

```bash
uv run loto3 campaign --output unused --plan-only
```

Run:

```bash
RUN_ID="unified-$(date +%Y%m%d-%H%M%S)"
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output "artifacts/unified-campaign/${RUN_ID}"
```

For all six games, expected inputs are `mini.csv`, `loto6.csv`, `loto7.csv`, `bingo5.csv`, `numbers3.csv`, and `numbers4.csv`.

Before execution preserve the raw source as an immutable snapshot, record its hash, verify chronology/duplicates/missing/non-finite/domain legality, reject future-derived features, and use a new output directory.

## Scientific interpretation

Primary metric: `Hit@±1 / hit_at_1`.

Also inspect per-position Hit@±1, all-position Hit@±1, MAE, MSE, RMSE, every configured seed, population variance/worst-seed statistics, and mandatory baselines.

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

Do not select a model from its best seed only. A complete matrix does not imply universal execution success; preserve `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS`, and `NON_STANDALONE_METHOD` rows.

## Prediction lock

For each evaluated game/candidate/seed, verify the prediction lock exists, records `actuals_known=false`, and retains SHA-256/timestamp evidence before the corresponding actual is read for scoring.

Expected campaign artifacts include:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/
prediction_locks/
SHA256SUMS
```

Never overwrite an existing evidence directory.

## Decoder/routing behavior

Merged PR #249 provides explicit `MAP` and `WITHIN_TAU` constrained select-game objectives. Merged PR #250 routes probability-bearing unified-campaign candidate estimators through family-specific WITHIN_TAU decoders:

- digit family: window-mass WITHIN_TAU probability decoding;
- select family: legal constrained WITHIN_TAU DP;
- point-only workers: no fabricated PMF; point legalisation remains explicit;
- candidate adapter: `row-normalized-slot-binary-probability-v1`, not a native categorical PMF;
- decoder/distribution identities are retained in runtime evidence and sealed evaluation lineage.

Treat this as implementation/routing evidence only. Real OOF improvement must still be measured chronologically.

## Runtime certification

For any claimed real model execution verify dependency import, load, valid input, inference completion, output shape, finite values, requested/observed device, GPU PID/VRAM when CUDA is claimed, explicit CPU fallback, and reload inference when persistence certification requires it.

`registered`, `dependency declared`, `runtime certified`, and `forecast accurate` are separate states.

## Holdout and Prospective

Default state is closed.

Do not open Holdout until approved development/OOF protocol, multi-seed aggregation, mandatory baseline comparisons, leakage checks and prediction-lock evidence are complete and reviewed. Prospective predictions must be sealed before future actuals exist. Neither gate automatically authorizes promotion.

## Current scientific workstreams

- GitHub #239: Timer Base 84M leakage-safe OOF.
- GitHub #118: Timer-S1 immutable runtime/certification PR-B.

## Failure handling

Preserve failure rows/logs, classify the failure, never rewrite old prediction/evidence artifacts, fix on a new branch/run, execute focused validation first, then full CI, and use a new Run ID/output directory.
