# Feature Specification: Full-Coverage Multi-Game Forecasting Platform

**Feature Branch**: `001-full-coverage`

**Created**: 2026-07-30

**Status**: Implemented

**Input**: User description: "欠落している機能を改修してすべて網羅的に確実かつ正確かつ頑健に実行できるようにしてください / その他追加したほうがよい機能やモデルなどを追加実装してフル実装して"

## Problem Statement

An independent audit of v2.1.0 verified its integrity claims (13/13 manifest hashes, 202 ZIP
entries, 19 OpenAPI paths, 65% coverage, 84 catalog rows) but found ten structural defects
that the release report did not disclose. Four were severity-critical:

1. Two disagreeing checksum manifests; `sha256sum -c verification/SHA256SUMS` reported 14 of
   82 FAILED, indistinguishable from tampering.
2. The test suite's verdict depended on whether `optuna` happened to be installed (53 passed
   with it, 52 passed + 1 failed without), because a blanket `except Exception` converted a
   missing import into a behaviour change.
3. The statistical-acceptance layer (`pace_gate`, `promotion`, `calibrators`, `stacking`) was
   dead code, reachable only from tests. `calibrators` had 0% coverage. The leaderboard ranked
   on a raw composite with no significance test and no dispersion columns.
4. The forecasting and evaluation core hard-coded 37 numbers and 7 slots, so of the six games
   whose data pipeline was verified, only Loto7 could actually be forecast.

Separately, the model catalog was materially incomplete against upstream: 84 registered rows
against 132 available estimators in the four Nixtla libraries alone.

## User Scenarios & Testing

### User Story 1 - Forecast and evaluate any of the six games (Priority: P1)

A researcher points the platform at ミニロト, ロト6, ロト7, ビンゴ5, ナンバーズ3 or
ナンバーズ4 and gets a complete evaluation: positional metrics, set overlap where meaningful,
probabilistic scores, and the exact theoretical bounds for that game's combinatorics.

**Why this priority**: This is the headline claim of v2.1.0 that was false in practice. Every
other improvement is worth less if the platform still only handles one game.

**Independent Test**: Run `loto3 research --game <g>` for all six keys. Each must complete with
`status=SUCCEEDED` and a `protocol_hash` specific to that game's geometry. Delivers value on
its own even with no new models.

**Acceptance Scenarios**:

1. **Given** a normalised ナンバーズ4 frame, **When** a research run executes, **Then** metrics
   are computed over 4 slots of 0–9 with repeats permitted and leading zeros preserved.
2. **Given** a ロト6 frame, **When** a model emits a non-ascending combination, **Then** the
   prediction is projected onto the legal space and the projection is visible in the metrics
   rather than raising.
3. **Given** any game, **When** the exact bounds are requested, **Then** the MAE floor, MSE
   floor and within-tau ceiling are returned from Fraction arithmetic, and the MAE-optimal and
   hit-rate-optimal predictors are shown to be different predictors.

### User Story 2 - Refuse to name a champion that did not win (Priority: P1)

A researcher sweeps N models against a baseline. The leaderboard reports, for every row, the
sample size, the dispersion, a bootstrap interval, and a multiplicity-corrected p-value. When
nothing beats the baseline the verdict is `NO_MODEL_BEATS_BASELINE` and `champion` is `null`.

**Why this priority**: On an i.i.d. target the correct answer is "no model won". A leaderboard
that always names a rank-1 winner cannot express the correct answer, and v2.1.0's did not.

**Independent Test**: Feed 12 statistically identical models plus a baseline. Assert
`champion is None` and `n_significant == 0`. Then plant one genuinely better model and assert
it is found and named.

**Acceptance Scenarios**:

1. **Given** 100 candidate models, **When** ranked at alpha=0.05 without correction, **Then**
   the family-wise false-positive probability exceeds 99% — asserted directly as a test.
2. **Given** results carrying two different `protocol_hash` values, **When** a leaderboard is
   requested, **Then** `ProtocolMismatch` is raised rather than a merged ranking returned.
3. **Given** an objective that weights `ece` without any sharpness term, **When** the composite
   is computed, **Then** it raises, because a constant predictor attains `ece == 0` exactly.
4. **Given** a model that supplies only aggregate metrics, **When** ranked, **Then** it appears
   in `unranked` rather than being ranked on a mean.

### User Story 3 - Make leakage falsifiable (Priority: P2)

Every research run executes negative controls. A label-permuted refit, a time-shifted refit,
and an exact causality audit of the feature builder. Any control scoring above chance sets
`SENTINEL_TRIPPED` and blocks promotion.

**Why this priority**: Good scores are indistinguishable from leakage by inspection. Without a
negative control the platform cannot tell the two apart, and the whole evaluation stack is
unfalsifiable.

**Independent Test**: Register a deliberately leaking predictor that returns the labels
verbatim. Assert the permutation control trips and promotion is blocked.

**Acceptance Scenarios**:

1. **Given** a centred rolling window in a feature builder, **When** the causality audit runs,
   **Then** it reports the offending column indices exactly, independent of sample size.
2. **Given** no controls trip, **When** the suite reports, **Then** the interpretation says
   "absence of evidence only" and does not claim the pipeline is leak-free.

### User Story 4 - Register every upstream estimator with traceable provenance (Priority: P2)

The catalog covers all 37 neuralforecast models, 36 AutoModels, 41 statsforecast models, 8
mlforecast Auto estimators, 10 reconciliation methods, and 21 pinned-repo TSFMs. Every count in
every document is generated from the catalog.

**Why this priority**: 74 estimators were missing, including the entire Croston/ADIDA/IMAPA
intermittent family — which is the natural model class for per-number occurrence — and
`SeasonalNaive`, the only reference that has ever mattered in this problem.

**Independent Test**: Assert list lengths against upstream `__all__`, assert library subtotals
sum to the total, assert no `model_id` collides, assert every AutoModel has a base estimator.

**Acceptance Scenarios**:

1. **Given** a TSFM whose commit SHA has not been verified, **When** it is registered, **Then**
   `revision` is `None` and `revision_status` is `UNPINNED` — a plausible-looking SHA is never
   substituted.
2. **Given** the TTM family, **When** registered, **Then** the Apache-2.0
   `ibm-granite/granite-timeseries-ttm-r2` checkpoint is used and the non-commercial
   `ibm-research/ttm-r3` is absent from the catalog entirely.

### User Story 5 - Act on the one strategy that has an edge (Priority: P3)

Because the payout is pari-mutuel, expected value decomposes into an unimprovable win
probability and an improvable co-winner count. The platform fits a popularity surface from
realised prize-tier winner counts and suggests low-popularity combinations — but only when a
permutation test says the surface carries signal.

**Why this priority**: It is the sole actionable finding from eight PDCA backtesting cycles.
Priority P3 because it is orthogonal to forecasting quality and delivers value only after
US1–US4 make the platform trustworthy.

**Independent Test**: Plant a calendar-date popularity signal; assert it is detected and
suggestions are ordered. Then feed pure noise; assert `usable is False` and `suggest_unpopular`
returns an empty list.

**Acceptance Scenarios**:

1. **Given** any combination, **When** its expected value is decomposed, **Then** the win
   probability is reported as identical for every legal combination and explicitly labelled
   "not improvable".
2. **Given** a fitted surface, **When** results are rendered, **Then** the caveat states that a
   payout multiplier does not make the bet +EV.

### User Story 6 - Verify the artifact against itself (Priority: P2)

One manifest, `INTEGRITY.json`, with a self-digest. `loto3 integrity check` distinguishes
MODIFIED from MISSING from UNTRACKED and exits non-zero on any of them.

**Independent Test**: Generate, then in three separate trees modify one file, delete one file,
and add one file. Assert the three distinct statuses.

**Acceptance Scenarios**:

1. **Given** a file added after manifest generation, **When** verified, **Then** the status is
   `STALE_MANIFEST` and `modified` is empty — the v2.1.0 confusion is impossible to reproduce.
2. **Given** a tampered manifest, **When** verified, **Then** the self-digest mismatch is
   reported independently of the per-file results.

### Edge Cases

- Fewer development rows than `min_train_size + gap + test_size` → raise with the arithmetic
  shown, never return zero folds silently.
- A model raising during a fold → recorded in `warnings` and `unranked`, run continues,
  status becomes `PARTIALLY_SUCCEEDED`.
- Calibration set too small to certify the requested conformal level → report the attainable
  guarantee `n/(n+1)`, not the requested one.
- `mint_shrink` requested without in-sample residuals → downgrade to `wls_struct` and set
  `downgraded_from_mint_shrink: true`.
- Popularity avoidance requested for a digit game → raise, because the strategy is defined for
  select-family games only.

## Requirements

### Functional

- **FR-001** All six games forecastable end to end; no universe size or slot count outside
  `loto.game`.
- **FR-002** Exact theoretical bounds per game, reporting MAE floor, MSE floor and within-tau
  ceiling as three distinct predictors.
- **FR-003** `protocol_hash` computed before any model executes; cross-protocol comparison
  raises.
- **FR-004** Multiplicity correction mandatory: Holm, Benjamini-Hochberg, Romano-Wolf.
- **FR-005** Leaderboard rows carry n, sd, se, bootstrap interval, raw and adjusted p.
- **FR-006** Negative controls executed every run; tripping blocks promotion.
- **FR-007** Distribution-free intervals via split conformal, plus ACI under drift.
- **FR-008** Catalog ≥ 132 estimators with computed counts and recorded primary sources.
- **FR-009** Hierarchical reconciliation with verified zero coherence error.
- **FR-010** Provenance gate rejecting null or inconsistent lineage columns.
- **FR-011** robots.txt honoured; per-host rate limiting enforced.
- **FR-012** Single self-verifying integrity manifest with three distinct failure statuses.

### Non-Functional

- **NFR-001** `pytest -q` green under `--extra dev` alone (hermeticity).
- **NFR-002** Core dependency set unchanged: numpy, pandas, pydantic, scikit-learn, scipy,
  PyYAML, prometheus-client.
- **NFR-003** Optional packages absent → `UNAVAILABLE` with the exact import error; never a
  substituted model.
- **NFR-004** Every degraded path emits a typed status record.

## Success Criteria

- **SC-001** Six of six games complete a research run. *(met: `test_run_completes_for_every_game`)*
- **SC-002** Zero false champions on i.i.d. input. *(met: `test_no_champion_on_pure_noise`)*
- **SC-003** Catalog total > 84 with self-consistent subtotals. *(met: 174)*
- **SC-004** Test count and hermeticity both improved. *(met: 53 → 251, verdict
  environment-independent)*
- **SC-005** Exactly one checksum manifest in the artifact. *(met: `verification/SHA256SUMS`
  and `api/openapi.json` removed)*

## Out of Scope

- Live HTTP acquisition against loto-life.net (implemented and robots-aware, not exercised).
- GPU training of the 73 neuralforecast estimators on RTX 5070 Ti.
- PostgreSQL, MLflow server, Ray cluster, Grafana/Loki/Tempo, Slack/SMTP delivery.
- Holdout unsealing and formal champion promotion.

These remain `IMPLEMENTED; not certified` and are listed in `docs/IMPLEMENTATION_STATUS_V3.md`.
