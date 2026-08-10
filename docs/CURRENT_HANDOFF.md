# Current Handoff

```text
status_class: AUDITED_SNAPSHOT
as_of: 2026-08-10T20:23+09:00
repository: arumajirou/loto_forecast_platform
code_audit_base_sha: 2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
source_of_truth: live GitHub + repository code/config + exact-head CI evidence
```

## Start here

1. `README.md`
2. `docs/CAPABILITIES_AND_OPERATIONS.md`
3. `docs/STATUS.md`
4. `docs/MODEL_EXECUTION_MATRIX.md`
5. `docs/UNIFIED_EVALUATION_CAMPAIGN.md`
6. `docs/CURRENT_VERIFICATION_REPORT.md`
7. `docs/CURRENT_RUNBOOK.md`
8. `docs/REQUIREMENTS.md`
9. `docs/SPECIFICATION.md`
10. `docs/ARCHITECTURE.md`
11. `docs/TEST_PLAN.md`

## Functional main state audited

```text
main=2d27b7f6e82035c3405e3dd88c99c2b5b282f2d8
```

Recent functional sequence:

```text
#248 unified all-model × all-game development campaign
#249 select MAP/WITHIN_TAU decoder
#250 family-aware candidate probability routing
#251 previous documentation alignment
#252 geometry-general metrics / hard-code gate
#253 theory-aware promotion eligibility v2
#254 paired-score power/MDE planning
```

Open PR search was 0 immediately before this documentation-refresh branch was created.

## Current model/evaluation surface

Canonical six-game comparison:

```bash
uv run loto3 campaign --output unused --plan-only

uv run loto3 campaign \
  --input-dir /path/to/canonical-csv-directory \
  --output /path/to/new-run-directory
```

The campaign is coverage-complete by preserving explicit failure/non-route rows; it does not guarantee 174 × 6 successful execution.

Broad forecast inventory: 174 entries.  
Separate probabilistic catalog: 72 models.  
Shared executable model inventory: `uv run loto models list`.

## Current metrics/decoder state

- Hit@±1 is primary.
- Geometry-general metrics now support all six games.
- Select `mean_hits` uses set overlap.
- Numbers3/4 `mean_hits` uses exact positional equality.
- Probability-bearing candidates use family-specific WITHIN_TAU decoding.
- Point-only models remain point-only.
- Distribution/decoder identity is retained in evaluation evidence.

## Theory-aware target state

`TheoryAwareThreshold` supports:

```text
absolute
excess_vs_iid_null
```

IID-null reference is an exact optimum under the declared null distribution, not a universal claim about arbitrary biased processes.

Targets that imply invalid probability or exceed an absolute null ceiling without an explicit alternative hypothesis fail closed.

## Promotion state

Promotion v2:

- binds policy game to sealed score `game_id`;
- fixes current evidence tolerance to tau=1;
- derives an effective absolute Hit@±1 target;
- checks aggregate/worst Prospective windows, degradation and all required baselines;
- never performs automatic promotion/retraining/registry write.

All-pass result means `ELIGIBLE_FOR_HUMAN_APPROVAL`, not `PROMOTED`.

## Power/MDE state

`paired-score-normal-approximation-v1` can compute required paired draws, MDE and deterministic power curves before the target evaluation window.

The score-difference SD must be fixed from allowed development/pilot evidence or a declared simulation before the target window. This is planning evidence only.

## Runtime/library state

Use `docs/MODEL_EXECUTION_MATRIX.md` for current routing details.

Key reminders:

- StatsForecast: 41 broad, 8 explicit shared IDs.
- MLForecast Auto: 8 broad, 2 direct shared MLForecast IDs.
- NeuralForecast: 37 fixed broad + 36 official AutoModels; shared fixed subset is narrower.
- AutoGluon: isolated subprocess/provider lane.
- BasicTS / Time-Series-Library / Merlion / sktime: separate provider/campaign lanes.
- GluonTS shared route is currently CPU-configured; do not claim shared CUDA from registration.
- TSFM aggregate runtime audit currently records 21 total / 19 runtime-certified exact identities.
- Runtime certification is not OOF superiority.

## Open scientific/runtime work

### #239 Timer Base 84M OOF

Formal leakage-safe real-data OOF remains open. Runtime certification does not close it.

Required order:

```text
OOF development evidence
-> Holdout authorization
-> Prospective seal/score
-> promotion eligibility
-> human approval
```

### #118 Timer-S1 PR-B

Immutable provenance, remote-code review, isolated runtime, real load/inference, device evidence and reload/reproducibility remain open runtime/certification work.

## Before next scientific execution

1. Re-fetch live main and open PR/issues.
2. Fix immutable data snapshot and hash.
3. Fix protocol/result-affecting config.
4. Plan model × game matrix.
5. Measure host CPU/RAM/GPU/storage and set resource budget.
6. Fix seed inventory.
7. Use a new Run ID/output directory.
8. Run baselines and models on chronological development folds.
9. Verify prediction locks precede actual reads.
10. Inspect failures; do not drop them.
11. Aggregate all seeds and compare baselines.
12. Use MDE/power planning before opening a target window when effect detectability matters.
13. Do not open Holdout without explicit authorization.

## Before next GitHub mutation

- re-fetch main/head/base;
- compare ahead/behind;
- inspect changed files;
- verify exact-head/current-base CI;
- check review threads;
- use expected-head merge guard;
- never represent queued/cancelled Actions as PASS.

## Safe conclusions

A complete campaign may conclude no model beats baseline. `champion=null`, `NOT_ELIGIBLE`, or a runtime/provider block are valid evidence outcomes.
