# Repository Status

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
source_of_truth: live GitHub state + current code/config + exact-head CI evidence
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

Live GitHub state takes precedence after the timestamp above. The SHA identifies the functional code state audited before this documentation-only branch.

## Executive status

- Default branch: `main`.
- Functional code audit base: `2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8`.
- Open PR search at the start of this documentation refresh: **0**.
- Current open GitHub scientific/runtime issues found in the repository audit: **#118 Timer-S1 PR-B** and **#239 Timer Base 84M OOF**.
- Canonical six-game geometry is implemented for `mini`, `loto6`, `loto7`, `bingo5`, `numbers3`, `numbers4`.
- Unified all-model × all-game **development** campaign is callable through `uv run loto3 campaign`.
- Broad generated forecast inventory remains **174 entries** at this code boundary.
- Separate probabilistic platform exposes a **72-model** catalog.
- Hit@±1 remains the primary comparison metric.
- Geometry-general metrics now preserve select set-overlap semantics and digit positional semantics.
- Probability-bearing campaign candidates use family-specific Hit@±1/WITHIN_TAU decoding; point-only routes remain point-only.
- Theory-aware Hit@±1 threshold semantics are implemented for new promotion evidence without rewriting historical v1 evidence.
- Pre-experiment paired-score MDE/power planning is implemented.
- Holdout: **CLOSED / NOT CLAIMED AS EVALUATED BY THIS MERGE/DOCUMENTATION SEQUENCE**.
- Prospective: **CLOSED / NOT CLAIMED AS EVALUATED**.
- Champion: **NONE AUTHORIZED BY CURRENT DOCUMENTATION**.
- Automatic promotion/retraining/registry write: **FORBIDDEN by current promotion policy contracts**.

## Recent main sequence

| PR | Main SHA | Result / evidence boundary |
|---|---|---|
| #248 | `aae45ba9294499f51cc5f1564de1c6ccf5814230` | unified all-model × all-game development campaign |
| #249 | `83f72d2fab2f5b060f0e42e68b87f8d2c6b4ac7f` | explicit MAP/WITHIN_TAU constrained select decoder |
| #250 | `8430d9f507ba735bf1df69930e057c974752bfdb` | candidate probability routing to family-aware WITHIN_TAU decoder |
| #251 | `5469410c4af679369ab65241c97ff4c4eaab39f2` | prior documentation alignment snapshot |
| #252 | `8c87356d6aeb776e47c06635592071a6a54014fd` | geometry-general metrics/hard-code gate; digit positional hit semantics fixed |
| #253 | `5c44cc866af36f3bbb44582263ff54bf392c3f10` | theory-aware promotion eligibility v2; sealed game identity and schema-aware evidence |
| #254 | `2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8` | paired-score power/MDE planning; invalid low-power regime fails closed |

PRs #252–#254 were merged serially after exact-head/current-main Linux CI and review-thread gates. #254 final CI used the merge ref `Merge 218fa3b4... into 5c44cc86...` and passed format, lint, compile, full pytest, clean-tree and cleanup before squash merge.

## Capability interpretation

Do not compress the following stages into a single “available” field:

```text
REGISTERED
-> DEPENDENCY_DECLARED
-> IMPLEMENTED
-> SHARED_ROUTABLE or PROVIDER_ROUTABLE
-> RUNTIME_CERTIFIED
-> LOTTERY_COMPATIBLE
-> OOF_EVALUATED
-> HOLDOUT_EVALUATED
-> PROSPECTIVE_EVALUATED
-> PROMOTION_ELIGIBLE
-> HUMAN APPROVAL
```

The 174-entry broad catalog is a planning/inventory layer. It is not 174 proven shared workers or 174 proven winners.

## Unified campaign state

Primary command:

```bash
uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

Plan only:

```bash
uv run loto3 campaign --output unused --plan-only
```

The campaign:

- materializes every requested broad-catalog model × game pair once;
- keeps `FAILED`, `UNAVAILABLE`, `NOT_ROUTABLE`, `UNSUPPORTED_GAME`, `PARTIAL_SEEDS`, `NON_STANDALONE_METHOD` as visible evidence;
- evaluates seven mandatory baselines;
- retains every configured seed and summary variance/worst statistics;
- seals predictions with `actuals_known=false`, fsync and SHA-256 before matching actuals are read by the scoring stage;
- does not automatically open formal Holdout or Prospective.

`matrix_complete=true` means result-row coverage is complete. It does not mean every model/game pair succeeded.

## Geometry-general evaluation state

`loto.game.geometry` is the single source of truth for game shape and legality.

`loto.evaluation.metrics.evaluate_outcomes()` now evaluates every canonical family using its own semantics:

- select: `mean_hits` is set overlap;
- digits: `mean_hits` is exact positional equality, preserving order and repeated digits;
- all families: position MAE/MSE/RMSE, within-tau rate and all-position within-tau rate are geometry-width aware.

The older Loto7 `evaluate_draws()` API remains a compatibility wrapper.

## Decoder/routing state

Probability-bearing candidate route:

```text
slot-conditioned binary candidate output
-> row normalization
-> distribution identity = row-normalized-slot-binary-probability-v1
-> digits: positional window-mass WITHIN_TAU
-> select: legality-constrained WITHIN_TAU dynamic programming
-> legal point forecast
```

Point-only workers do not receive a fabricated PMF.

This is code/theory/routing evidence, not real-data evidence that the decoder improves every model.

## Theory-aware threshold state

`TheoryAwareThreshold` supports:

```text
absolute
excess_vs_iid_null
```

The exact IID-null reference is game/tau-specific. An absolute configured target above the IID-null ceiling fails closed unless an explicit alternative hypothesis is declared. The IID-null ceiling is documented as an exact optimum under that null distribution, not a universal bound for every possible biased process.

## Promotion state

Historical promotion schema v1 remains parseable without reinterpretation.

Promotion v2:

- requires an explicit game;
- fixes current promotion evidence tolerance to `tau=1`;
- resolves theory semantics into an absolute Hit@±1 threshold;
- requires sealed `game_id` evidence on Holdout and every Prospective window;
- rejects game mismatch;
- checks aggregate/worst-window target, degradation and mandatory baselines.

Even if all rules pass, the automated decision is only `ELIGIBLE_FOR_HUMAN_APPROVAL`.

```text
human_approval_required=true
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

## Power/MDE planning state

`loto.evaluation.power_analysis` implements `paired-score-normal-approximation-v1` for pre-experiment planning.

Capabilities:

- required paired draws for a declared positive effect;
- minimum detectable effect for a declared sample size;
- deterministic MDE curves;
- Bonferroni-adjusted planning alpha for multiplicity;
- fail-closed invalid effect/SD/draw-count/tail/low-power inputs.

`score_sd` is required from allowed development/pilot evidence or a declared simulation fixed before the target window. The output is planning evidence, not a p-value or promotion result.

## Model/runtime state

For detailed library-by-library routing use:

- `README.md`;
- `docs/CAPABILITIES_AND_OPERATIONS.md`;
- `docs/MODEL_EXECUTION_MATRIX.md`.

Current repository TSFM aggregate runtime evidence records 21 models and 19 runtime-certified identities in `audit/tsfm-runtime/runtime-status.json`. Runtime certification remains separate from lottery OOF quality.

## Current dependency boundary

Current `pyproject.toml` includes, among other contracts:

- Python `>=3.11,<3.14`;
- NeuralForecast `==3.2.0`;
- Torch `==2.9.1`;
- Transformers `==4.57.6`;
- Hugging Face Hub `==0.36.2`;
- FastAPI `>=0.141.1,<0.142` in API/full lanes;
- Ray Tune `>=2.56.1` in `full`;
- Uvicorn `>=0.52.1`;
- MLflow `>=3.15.1`;
- Ruff `>=0.16.1` in dev;
- GluonTS `>=0.17.0` in frameworks.

`uv.lock` is the committed lock authority. Isolated provider environments have independent dependency contracts by design.

## Open scientific/runtime work

### #239 — Timer Base 84M leakage-safe OOF

Runtime certification is not OOF. This issue remains the formal forecast-quality workstream. Required order remains development/OOF first, then separately authorized Holdout, then Prospective.

### #118 — Timer-S1 PR-B runtime/certification

Immutable upstream provenance, remote-code review, isolated runtime, real load/inference, device evidence and reload/reproducibility remain explicit runtime gates. This issue does not authorize OOF or accuracy claims.

## What is not established by this snapshot

- that every one of the 174 broad entries successfully executes on all six games;
- that a complete real-data 174 × 6 campaign has completed;
- that all 72 probabilistic models have completed formal lottery OOF;
- that every TSFM runtime-certified identity beats mandatory baselines;
- that WITHIN_TAU decoding improves every real OOF run;
- that lottery draws are non-IID;
- that Holdout or Prospective has been opened/completed;
- that a champion is authorized;
- that promotion has occurred.

A valid formal result can be `NO_MODEL_BEATS_BASELINE` with no champion.
