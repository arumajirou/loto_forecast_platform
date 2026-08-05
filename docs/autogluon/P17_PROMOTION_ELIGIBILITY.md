# P17 multi-window promotion eligibility gate

## Purpose

P17 consumes one verified P16 Holdout scoring artifact and multiple verified P16 Prospective
scoring artifacts. It decides only whether the unchanged shadow candidate is eligible to enter a
separate human-approval process.

A successful P17 decision is not model promotion, registration, deployment, or approval. The most
permissive state is:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
human_approval_required=true
human_approval_granted=false
automatic_promotion=false
automatic_retraining=false
registry_write_allowed=false
promotion_status=NOT_PROMOTED
```

## Required upstream evidence

P17 requires:

- exactly one verified P16 Holdout scoring directory;
- one or more verified P16 Prospective scoring directories;
- P16 `status=PASS` for every source;
- one unchanged selected candidate across Holdout and every Prospective window;
- unique source run IDs;
- non-overlapping Holdout and Prospective draw IDs;
- complete per-prediction selected-candidate seed and draw coverage;
- at least three selected-candidate seeds in every source;
- the exact seven required baselines in every source;
- upstream `automatic_promotion=false` and `automatic_retraining=false`;
- valid P16 manifests, report self-hashes, and `SHA256SUMS`.

Every upstream source tree is fingerprinted before evaluation and again before publication. Any
change aborts the P17 run.

## Default eligibility policy

The default policy requires:

- at least three Prospective windows;
- at least three unique Prospective draws;
- every Prospective window to be `STABLE`;
- aggregate Prospective Hit@±1 of at least `0.90`;
- worst-window Prospective Hit@±1 of at least `0.90`;
- Holdout-to-Prospective Hit@±1 drop no greater than `0.05`;
- Holdout-to-Prospective MAE increase no greater than `0.50`;
- selected-candidate Hit@±1 no lower than every baseline;
- selected-candidate MAE no higher than every baseline.

The rules are evaluated in the documented order. The first failed rule becomes the deterministic
`reason_code`. A policy failure produces `NOT_ELIGIBLE`; it does not invalidate otherwise correct
evidence.

## Multi-seed aggregation

P17 reads the P16 per-prediction metric rows. It first aggregates by candidate and seed across all
Prospective draws, then aggregates across seeds. It preserves:

- mean Hit@±1;
- Hit@±1 variance;
- worst-seed Hit@±1;
- mean all-position Hit@±1;
- mean MAE;
- MAE variance;
- worst-seed MAE;
- mean MSE;
- mean RMSE.

No best-seed-only selection is permitted. Window-level summaries are also retained so one weak
window cannot be hidden by a stronger aggregate.

## Required baselines

The exact baseline set is:

```text
baseline_random
baseline_fixed
baseline_mean
baseline_median
baseline_last
baseline_frequency
baseline_ar1
```

The selected candidate must have aggregate Hit@±1 greater than or equal to each baseline and
aggregate MAE less than or equal to each baseline.

## Decisions

### Eligible

All rules pass:

```text
ELIGIBLE_FOR_HUMAN_APPROVAL
reason_code=ALL_RULES_PASS
```

This authorizes only preparation for a separate human review. It does not grant approval.

### Not eligible

The first failed rule produces:

```text
NOT_ELIGIBLE
reason_code=<first failed rule ID>
```

Examples include insufficient windows, warning or critical drift, Hit@±1 below target, excessive
Holdout degradation, or a baseline outperforming the candidate.

## Durable evidence

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

The independent verifier recomputes aggregate metrics, ordered rules, the decision, and the response
from `WINDOW_EVIDENCE.json` and the sealed policy. It also rechecks candidate identity, unique run
IDs, draw non-overlap, source stages, required candidates, manifests, and file hashes.

## CLI

Create a decision:

```bash
PYTHONPATH=src python scripts/run_autogluon_p17_promotion.py create \
  --holdout-score artifacts/autogluon-p16/<holdout-score> \
  --prospective-score artifacts/autogluon-p16/<prospective-score-1> \
  --prospective-score artifacts/autogluon-p16/<prospective-score-2> \
  --prospective-score artifacts/autogluon-p16/<prospective-score-3> \
  --policy configs/autogluon_campaign/p17_promotion_eligibility_policy.json \
  --output artifacts/autogluon-p17/<run-id> \
  --run-id <run-id>
```

Verify a decision:

```bash
PYTHONPATH=src python scripts/run_autogluon_p17_promotion.py verify \
  --run artifacts/autogluon-p17/<run-id>
```

Exit code `0` is reserved for `ELIGIBLE_FOR_HUMAN_APPROVAL`. `NOT_ELIGIBLE`, malformed input,
source tampering, and verification failure return exit code `2`.

## Certification boundary

The current authoring tests use synthetic, correctly hashed P16 scoring bundles. They verify the
P17 aggregation, rules, decisions, deterministic output, CLI behavior, and tamper rejection. They
do not certify:

- real AutoGluon 1.5.0 execution;
- a real OOF-selected candidate;
- real Holdout or Prospective P16 scoring artifacts;
- real eligibility for human approval;
- human approval, registry mutation, promotion, or deployment;
- external trusted timestamping or signatures;
- Ruff, mypy, full repository pytest, GitHub Actions, or GPU evidence.
