# P10 Shadow Canary Evaluation

## Purpose

P10 scores predictions that were already fixed by an active P9 shadow canary.
It runs only after verified actual values become available. It never loads a
model, retrains, re-predicts, changes the primary binding, publishes a canary
prediction, or executes rollback.

The strongest successful result is only:

```text
ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW
primary_promotion_executed=false
primary_binding_changed=false
prediction_publication_allowed=false
```

A separate P11 review and transaction are required before any primary change.

## Required window evidence

Each shadow window contains:

- the P9 activation ID and shadow candidate ID;
- unique, non-overlapping draw IDs;
- position-specific value ranges;
- a prediction lock timestamp and canonical SHA-256 seal;
- a later actual reveal timestamp and actual-source SHA-256;
- a history snapshot SHA-256 and prediction-code SHA-256;
- one deployed shadow prediction;
- all required baseline predictions;
- verified actual values.

The lock covers draw IDs, geometry, all predictions, history and code hashes,
and the statement that actuals were unknown and predictions were not public.
Changing a locked prediction invalidates the window.

Actual reveal time must be later than prediction lock time. P10 evaluation time
must be later than every actual reveal time.

## Required baselines

P10 requires the exact baseline inventory:

- `random`;
- `fixed`;
- `mean`;
- `median`;
- `last`;
- `frequency`;
- `seasonal_naive` as the statistical baseline.

The random baseline must include seeds `1`, `2`, and `3`. P10 stores seed mean,
population variance, and worst values. It never selects the best random seed.
Other candidates are represented once because they are deterministic locked
predictions.

## Metrics

Hit@±1 is the primary metric. P10 also stores:

- position-level Hit@±1;
- all-position Hit@±1;
- MAE;
- MSE;
- RMSE;
- weighted mean across windows;
- weighted population variance across windows;
- worst window;
- model-versus-baseline deltas.

Value-level metrics are weighted by the number of predicted values. All-position
and position metrics are weighted by draw count.

## Default decision policy

The formal default policy requires:

- at least three unique windows;
- at least three unique draws;
- weighted Hit@±1 of at least `0.90`;
- worst-window Hit@±1 of at least `0.90`;
- weighted MAE no greater than `1.0`;
- shadow Hit@±1 no worse than every baseline;
- shadow MAE no worse than every baseline;
- strict improvement in Hit@±1 or MAE over at least one baseline.

The first failed rule creates one deterministic decision:

```text
BLOCKED_INSUFFICIENT_WINDOWS
BLOCKED_INSUFFICIENT_DRAWS
REJECTED_PRIMARY_HIT_TARGET
REJECTED_WORST_WINDOW
REJECTED_MAE_LIMIT
REJECTED_BASELINE_SUPERIORITY
REJECTED_NO_STRICT_BASELINE_IMPROVEMENT
ELIGIBLE_FOR_PRIMARY_PROMOTION_REVIEW
```

A rejection does not automatically remove the canary. It recommends a separate
human review of canary continuation or deactivation.

## Shadow window file

A window is a JSON file using the `ShadowEvaluationWindow` schema. Generate the
`prediction_lock_sha256` before actual values are inserted by hashing the
canonical `prediction_lock_payload` from
`loto.sktime_campaign.canary_evaluation`.

Every prediction row must state:

```json
{
  "actuals_known_at_prediction": false,
  "prediction_scope": "SHADOW_ONLY"
}
```

The deployed shadow candidate uses `seed: null`. Random baseline rows use seeds
`1`, `2`, and `3`. No other baseline may carry a seed.

## Execute P10

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

export SKTIME_P10_P9_EVIDENCE_DIR="/absolute/path/to/p9/shadow-canary-activation"
export SKTIME_P10_WINDOW_FILES="$(
  printf '%s:%s:%s' \
    /absolute/path/to/window-1.json \
    /absolute/path/to/window-2.json \
    /absolute/path/to/window-3.json
)"
export SKTIME_P10_EVALUATED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

bash scripts/start_sktime_p10_certification_tmux.sh
```

Attach to the protected terminal:

```bash
tmux attach -t sktime-p10-canary-evaluation
```

## Durable evidence

A successful evaluation run creates:

- `REQUEST_METADATA.json`;
- `P9_LINEAGE.json`;
- `WINDOW_EVIDENCE.json`;
- `WINDOW_METRICS.json`;
- `AGGREGATED_METRICS.json`;
- `BASELINE_COMPARISON.json`;
- `RULE_EVALUATION.json`;
- `PRIMARY_PROMOTION_REVIEW_DECISION.json`;
- `response.json`;
- `ARTIFACT_MANIFEST.json`;
- `SHA256SUMS`.

The independent verifier recomputes all metrics, seed summaries, baseline
deltas, ordered rules, formal decision, manifest coverage, and SHA-256 values.

## Certification boundary

Authoring tests use synthetic windows. They do not prove that real P9 activation
occurred, predictions were truly fixed before actual publication, actual-source
identity is official, the 90% target is reached, a baseline is beaten, or a
primary promotion is safe. P10 never changes deployment state.
