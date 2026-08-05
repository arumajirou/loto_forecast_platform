# sktime P6 manual promotion eligibility gate

## Status

```text
IMPLEMENTATION=STACKED_DRAFT_PR
STAGE=MULTI_WINDOW_PROSPECTIVE_PROMOTION_GATE
AUTOMATIC_PROMOTION=false
AUTOMATIC_RETRAINING=false
REGISTRY_WRITE_ALLOWED=false
HUMAN_APPROVAL_REQUIRED=true
REAL_TARGET_EXECUTION=EXECUTION_PENDING
```

P6 consumes verified P0 through P4 evidence and multiple verified P5 monitoring
windows. It decides whether the frozen shadow candidate has enough evidence to
be presented for human approval.

P6 never promotes a model.

## Why P6 is separate

P5 deliberately separates prediction locking from post-reveal scoring and drift
monitoring. A single Prospective window is not sufficient for promotion.

P6 therefore requires multiple non-overlapping windows and evaluates:

- evidence integrity;
- runtime certification;
- data-quality and leakage status;
- seed-policy compliance;
- pre-actual prediction locking;
- weighted Prospective performance;
- worst-window performance;
- Holdout-to-Prospective regression;
- every baseline comparison;
- drift severity.

## Upstream lineage

The request requires exact SHA-256 identities for:

```text
P0
P1
P2
P3
P4
```

Each P5 monitoring window contributes:

- monitoring bundle SHA-256;
- prediction-lock seal SHA-256;
- independently sourced actuals SHA-256;
- prediction seal time;
- actual reveal time;
- draw identities;
- shadow candidate ID;
- drift status;
- recommendation;
- candidate metrics;
- baseline metrics.

Window IDs, prediction-lock seals, and draw identities must be unique.

All windows must use the same shadow candidate selected by P3 OOF and retained
through P4 and P5.

## Default formal policy

```text
minimum_prospective_windows=3
minimum_total_draws=3
minimum_weighted_hit_at_1=0.90
minimum_worst_window_hit_at_1=0.90
maximum_hit_drop_from_holdout=0.05
maximum_mae_increase_from_holdout=0.50
maximum_warning_windows=0
maximum_critical_windows=0
require_all_baselines_beaten=true
```

Hit@±1 remains the primary metric.

## Multi-window aggregation

Window metrics are weighted by the number of draws in each window.

P6 retains:

- weighted mean;
- weighted population variance across windows;
- worst value.

For Hit@±1 metrics, worst means the minimum observed worst value.

For MAE, MSE, and RMSE, worst means the maximum observed worst value.

## Rule order

P6 evaluates rules in this order:

1. minimum Prospective windows;
2. minimum total draw count;
3. warning-window limit;
4. critical-window limit;
5. weighted Hit@±1 target;
6. worst-window Hit@±1 target;
7. Holdout Hit@±1 regression limit;
8. Holdout MAE regression limit;
9. superiority to every available baseline.

The first failed rule determines the blocked decision.

Possible outcomes include:

```text
BLOCKED_INSUFFICIENT_WINDOWS
BLOCKED_INSUFFICIENT_DRAWS
BLOCKED_WARNING_DRIFT
BLOCKED_CRITICAL_DRIFT
BLOCKED_HIT_TARGET
BLOCKED_WORST_CASE
BLOCKED_HOLDOUT_REGRESSION
BLOCKED_BASELINE_SUPERIORITY
ELIGIBLE_FOR_HUMAN_APPROVAL
```

`ELIGIBLE_FOR_HUMAN_APPROVAL` is not a promotion.

## Required safety state

Every outcome records:

```text
human_approval_required=true
human_approval_granted=false
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

A later, explicitly authorized phase is required before any registry write or
production activation.

## Durable artifacts

```text
REQUEST_METADATA.json
UPSTREAM_LINEAGE.json
WINDOW_EVIDENCE.json
AGGREGATED_METRICS.json
RULE_EVALUATION.json
PROMOTION_DECISION.json
response.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

The verifier recomputes all aggregates, rules, the decision, manifest coverage,
and SHA-256 evidence.

## Stacked branch

P6 is implemented on:

```text
agent/sktime-promotion-gate-v1
```

Its base is the P0 through P5 branch:

```text
agent/sktime-forecasting-contract-v1
```

This protects the existing P5 implementation from concurrent overwrite and
keeps the promotion-governance diff reviewable.

## Target-host execution

P6 requires explicit evidence directories.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin agent/sktime-promotion-gate-v1
git switch agent/sktime-promotion-gate-v1
git pull --ff-only

export SKTIME_P0_EVIDENCE_DIR="/absolute/path/to/p0/evidence"
export SKTIME_P1_EVIDENCE_DIR="/absolute/path/to/p1/evidence"
export SKTIME_P2_EVIDENCE_DIR="/absolute/path/to/p2/evidence"
export SKTIME_P3_EVIDENCE_DIR="/absolute/path/to/p3/evidence"
export SKTIME_P4_EVIDENCE_DIR="/absolute/path/to/p4/evidence"

export SKTIME_P5_MONITOR_DIRS="$(
    printf '%s:%s:%s' \
        /absolute/path/to/p5-window-1 \
        /absolute/path/to/p5-window-2 \
        /absolute/path/to/p5-window-3
)"

bash scripts/start_sktime_p6_certification_tmux.sh
```

Monitor:

```bash
tmux attach -t sktime-p6-promotion-gate
```

## Authoring verification

The isolated P6 contract harness reports:

```text
promotion gate and rule tests: 16 passed
artifact and tamper tests: 8 passed
total focused tests: 24 passed
Python py_compile: PASS
Bash bash -n: PASS
source lines over 100 characters: 0
```

These checks do not certify target-host evidence, real Prospective performance,
or promotion eligibility.

## Boundaries

P6 does not:

- promote a candidate;
- write a model registry;
- deploy a model;
- retrain automatically;
- replace the P3 OOF-selected shadow candidate;
- choose a best seed after actuals;
- claim real-data accuracy;
- claim baseline superiority without verified real evidence;
- claim GitHub Actions success;
- claim merge readiness.

A later phase may implement a separately authorized registry transaction, but
only after explicit human approval and a second immutable approval record.
