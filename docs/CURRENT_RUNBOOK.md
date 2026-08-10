# Current Runbook

```text
status_class: DESIGN_CONTRACT
as_of: 2026-08-10T18:46+09:00
audited_main_sha: cfbe9f1cf379a68b4ad6ca2bc6d7793dbd828300
```

## Purpose

Use this runbook for repository maintenance and the unified development-only evaluation campaign. It does not authorize Holdout, Prospective or promotion.

## Repository preflight

Always start from live state rather than copied prose.

```bash
git fetch origin
git switch main
git pull --ff-only
uv lock --check
```

For every PR record live main SHA, PR base/head SHA, draft/mergeable state, changed files, ahead/behind relation, exact-head CI, and unresolved review threads. When dependency PRs share `pyproject.toml` or `uv.lock`, merge serially and regenerate/rebase the remaining PR after each merge. Use `expected_head_sha` for merges.

Queued, cancelled and failed Actions runs are not PASS.

## Repository validation

During implementation prefer focused tests/smokes. At the final merge gate use the repository-standard checks:

```bash
uv sync --locked --extra dev
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run python -m compileall -q src scripts tests
uv run pytest -q
```

## Unified campaign

Plan without executing models:

```bash
uv run loto3 campaign --output unused --plan-only
```

Run from canonical game CSVs:

```bash
RUN_ID="unified-$(date +%Y%m%d-%H%M%S)"
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output "artifacts/unified-campaign/${RUN_ID}"
```

Expected game files are `mini.csv`, `loto6.csv`, `loto7.csv`, `bingo5.csv`, `numbers3.csv`, and `numbers4.csv` when all games are requested.

Before execution preserve the raw source as an immutable snapshot, record its hash, verify chronology/duplicates/missing/non-finite/domain legality, reject future-derived features, and use a new output directory.

## Scientific interpretation

Primary metric:

```text
Hit@±1 / hit_at_1
```

Also inspect per-position Hit@±1, all-position Hit@±1, MAE, MSE, RMSE, all configured seeds, population variance/worst-seed statistics, and mandatory baselines.

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

A model must not be selected from its best seed only.

A complete result matrix does not imply universal success. Preserve `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS`, and `NON_STANDALONE_METHOD` rows.

## Prediction lock

For each evaluated game/candidate/seed, verify the prediction lock exists, records `actuals_known=false`, and retains SHA-256/timestamp evidence before the corresponding actual is read for scoring.

Expected final artifacts include:

```text
campaign_summary.json
model_game_results.csv
all_game_macro_summary.csv
protocols/
prediction_locks/
SHA256SUMS
```

Never overwrite an existing campaign evidence directory.

## Decoder objectives

Merged PR #249 provides explicit `MAP` and `WITHIN_TAU` select-game decoding. Treat decoder-theory tests as implementation evidence only; they do not prove real OOF gain.

PR #250 proposes routing probability-bearing unified-campaign candidates through the within-tau decoder. At this runbook audit it is pending current-main synchronization/exact-head verification. Re-fetch its live state before acting.

## Runtime certification

For any claimed real model execution verify dependency import, load, valid input, inference completion, output shape, finite values, requested/observed device, GPU PID/VRAM when CUDA is claimed, explicit CPU fallback, and reload inference where persistence certification requires it.

`registered`, `dependency declared`, and `runtime certified` are different states. Runtime certification is also separate from forecast accuracy.

## Holdout and Prospective

Default state is closed.

Do not open Holdout until the approved development/OOF protocol, multi-seed aggregation, mandatory baseline comparisons, leakage checks and prediction-lock evidence are complete and reviewed. Prospective predictions must be sealed before future actuals exist. Neither Holdout nor Prospective automatically authorizes promotion.

## Current scientific workstreams

- GitHub #239: Timer Base 84M leakage-safe OOF.
- GitHub #118: Timer-S1 immutable runtime/certification PR-B.

Check their live state before acting.

## Failure handling

If a model/provider fails, preserve the failure row/logs, classify the failure, never rewrite old prediction/evidence artifacts, fix on a new branch/run, execute focused validation first, then full CI, and use a new Run ID/output directory.
