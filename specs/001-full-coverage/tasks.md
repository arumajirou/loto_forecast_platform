# Tasks: Full-Coverage Multi-Game Forecasting Platform

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md)

**Organization**: grouped by user story so each group is independently deliverable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]** may run in parallel (different files, no dependency)
- All paths relative to the repository root

---

## Phase 1: Setup

- [x] T001 Copy the audited v2.1.0 tree as the v3 baseline; strip caches and coverage artefacts
- [x] T002 Create `src/loto/{game,reconciliation,strategy,verify}/` packages and `specs/001-full-coverage/`
- [x] T003 Bump `pyproject.toml` to 3.0.0, rename the distribution to `loto-forecast-platform`
- [x] T004 [P] Author `.specify/memory/constitution.md` with seven principles and four quality gates

## Phase 2: Foundational (blocks every user story)

- [x] T101 `src/loto/game/geometry.py` — `GameGeometry` with `select`/`digits` families, derived
      `universe_size`, `outcome_space`, `inclusion_vector_length`, `validate_outcome`
- [x] T102 Canonical `GEOMETRIES` table for all six games; `geometry_for` cached;
      `geometry_from_spec` bridging the existing `LotterySpec`
- [x] T103 [P] `tests/test_geometry.py` — including the AST gate asserting no geometry literal
      appears in any v3 core module

**Checkpoint**: `geometry_for("numbers4").outcome_space == 10_000` and the AST gate passes.

---

## Phase 3: US1 — Forecast any of the six games (P1)

- [x] T201 `evaluation/theory_general.py` — exact order-statistic pmf in `Fraction`; MAE floor,
      MSE floor, within-tau ceiling as three separate predictors; closed form for digit games
- [x] T202 `evaluation/metrics_general.py` — positional, set-overlap (select only),
      probabilistic with a uniform skill-score reference, ranking, MASE, sMAPE, reliability curve
- [x] T203 `contracts_general.py` — `contracts_for(game)` building pydantic classes via
      `create_model`; v1 `contracts.py` left intact
- [x] T204 [P] `tests/test_theory_general.py` — Loto7 floor `== 3.8337`; outcome spaces against
      published odds; metric trade-off strict for every select game
- [x] T205 [P] `tests/test_metrics_general.py` — every game shape accepted; wrong width rejected
      with the expected width named; SE reported; mass error detects an illegal probability vector

**Checkpoint**: US1 independently testable — bounds and metrics work for all six games.

---

## Phase 4: US2 — Refuse to name a champion that did not win (P1)

- [x] T301 `evaluation/protocol.py` — `ProtocolSpec`, 22 hashed fields, `protocol_hash`,
      `assert_comparable`, `ProtocolMismatch`. Missing hash treated as a distinct protocol
- [x] T302 `evaluation/multiplicity.py` — Holm, Benjamini-Hochberg, Romano-Wolf step-down
      bootstrap, paired bootstrap, `family_wise_false_positive_probability`
- [x] T303 `evaluation/leaderboard.py` — `ModelResult` requiring per-draw losses,
      `champion: LeaderboardRow | None`, `composite_score` rejecting an ece-only objective
- [x] T304 [P] `tests/test_protocol_hash.py` — stability, dict-order insensitivity, sensitivity
      to each of horizon / tau / game / folds / test_size / data_version / seeds
- [x] T305 [P] `tests/test_multiplicity.py` — 100-test FWER > 99%; Romano-Wolf finds nothing on
      40 noise candidates and finds the one planted effect
- [x] T306 [P] `tests/test_leaderboard.py` — no champion on noise; cross-protocol refused;
      aggregate-only models unranked; degenerate objective rejected

**Checkpoint**: US2 independently testable — ranking is significance-gated.

---

## Phase 5: US3 — Make leakage falsifiable (P2)

- [x] T401 `evaluation/sentinel.py` — permutation, time-shift, exact causality audit,
      `run_sentinel_suite` returning `promotion_allowed`
- [x] T402 `evaluation/conformal.py` — split conformal with honest guarantee downgrade, ACI,
      interval score, coverage report
- [x] T403 [P] `tests/test_sentinel.py` — leaking predictor trips the control; centred rolling
      window caught exactly; clean suite says "absence of evidence only"
- [x] T404 [P] `tests/test_conformal.py` — marginal coverage over 30 splits meets the guarantee;
      tiny calibration set reports `n/(n+1)`; interval score not gameable by widening

**Checkpoint**: US3 independently testable — leakage is detectable and coverage is certified.

---

## Phase 6: US4 — Register every upstream estimator (P2)

- [x] T501 `models/catalog_full.py` — verbatim `__all__` transcriptions; family assignment;
      FFT-precision annotation; multivariate `requires_n_series`; 21 TSFM entries with `repo_id`
- [x] T502 `catalog_counts()` computing every subtotal; `PRIMARY_SOURCES` recorded per library
- [x] T503 [P] `tests/test_catalog_full.py` — list sizes against upstream; subtotals sum to
      total; no id collision; every AutoModel has a base; TTM is Apache-2.0; ttm-r3 absent;
      unpinned revisions are `None` not fabricated
- [x] T504 Regenerate `docs/MODEL_CATALOG_V3.csv`, `docs/MODEL_INVENTORY.md`,
      `docs/THEORETICAL_BOUNDS.md` from code; delete the hand-typed v2.1 catalog and summary

**Checkpoint**: US4 independently testable — 174 estimators, all counts computed.

---

## Phase 7: US5 — Conscious-selection avoidance (P3)

- [x] T601 `strategy/popularity.py` — 10 behavioural features; weighted ridge on
      `log1p(winners)` with optional sales offset; permutation test; `usable` gate
- [x] T602 `expected_value_ratio` separating the unimprovable win probability from the
      improvable co-winner factor, with an explicit not-+EV caveat
- [x] T603 [P] `tests/test_popularity.py` — planted signal detected; pure noise returns no
      suggestions; digit games rejected; non-positive sales rejected

## Phase 8: US6 — Self-verifying integrity (P2)

- [x] T701 `verify/integrity.py` — `INTEGRITY.json` with self-digest; MODIFIED / MISSING /
      UNTRACKED distinguished; `main()` exiting non-zero on any failure
- [x] T702 Delete `verification/SHA256SUMS` (14/82 stale) and the superseded
      `FINAL_VERIFICATION.md` / `FINAL_INTEGRATED_V1_1_0.md`
- [x] T703 [P] `tests/test_integrity.py` — the three statuses in three separate trees; manifest
      tampering caught by the self-digest

## Phase 9: Cross-cutting repairs

- [x] T801 `data/provenance.py` + `tests/test_provenance.py` — reproduce the exact v2.1.0 defect
      (all-null `game` / `game_display_name` / `source_url`) and assert it now FAILs
- [x] T802 `data/robots.py` — per-host robots.txt cache, crawl-delay honoured, rate limiter,
      auditable decision log
- [x] T803 Narrow `_build_search_algorithm`'s blanket `except Exception` to `ImportError`;
      distinguish `library_default(optuna_absent)` from `library_default(ray_absent)`
- [x] T804 Declare `optuna` in the `dev` extra so the suite verdict no longer depends on the
      environment; verify by uninstalling optuna and rerunning
- [x] T805 `reconciliation/hierarchy.py` + tests — total → parity → decade → number summing
      matrix; BottomUp / TopDown / OLS / WLS-struct / MinT-shrink; coherence error asserted `< 1e-8`
- [x] T806 Remove the duplicate `api/openapi.json` (9 stale paths) leaving one API source

## Phase 10: Integration

- [x] T901 `orchestration/research_v3.py` — eight stages: protocol fingerprint → holdout split →
      causality audit → fold execution with mandatory controls → metrics → sentinel →
      conformal → PACE gate. Retains per-draw losses; records every degraded path
- [x] T902 Wire the previously-dead `pace_gate` into the run and stamp it with `protocol_hash`
- [x] T903 `_legalise` projecting illegal predictions onto the legal outcome space per family
- [x] T904 `cli_v3.py` — `games`, `theory`, `catalog`, `integrity`, `research`, `hierarchy`;
      JSON on stdout, POSIX exit codes; entry points `loto3` and `loto-integrity`
- [x] T905 [P] `tests/test_research_v3.py` — all six games; no champion on i.i.d.; controls
      injected; holdout sealed; failing model recorded not swallowed; illegal predictions projected
- [x] T906 [P] `tests/test_cli_v3.py` — every subcommand; the four previously-unforecastable
      games; integrity exit code 1 on tampering

## Phase 11: Release

- [x] T1001 Full suite green under `dev` alone — **251 passed**
- [x] T1002 Coverage measured and recorded
- [x] T1003 `docs/IMPLEMENTATION_STATUS_V3.md` and `README.md` regenerated
- [x] T1004 `INTEGRITY.json` generated as the sole manifest; `loto3 integrity check` green
- [x] T1005 Release ZIP produced and self-verified after fresh extraction

---

## Dependencies

```text
T101 ─┬─> T201 ─> T204        (US1)
      ├─> T202 ─> T205
      └─> T203
T301 ─┬─> T303 ─> T306        (US2)
T302 ─┘
T401, T402 ────> T403, T404   (US3)
T501 ─> T502 ─> T503, T504    (US4)
T601 ─> T602 ─> T603          (US5)
T701 ─> T702 ─> T703          (US6)
(T101, US1, US2, US3) ─> T901 ─> T904 ─> T905, T906 ─> T1001..T1005
```

## Task count

| phase | tasks | status |
|---|---:|---|
| Setup | 4 | complete |
| Foundational | 3 | complete |
| US1 | 5 | complete |
| US2 | 6 | complete |
| US3 | 4 | complete |
| US4 | 4 | complete |
| US5 | 3 | complete |
| US6 | 3 | complete |
| Cross-cutting | 6 | complete |
| Integration | 6 | complete |
| Release | 5 | complete |
| **total** | **49** | **complete** |
