# All-model / all-argument lifecycle audit

This audit fact-checks the model/argument compatibility table against executable evidence.

## What “all arguments” means

A Cartesian product of every possible value is unbounded and cannot be a short test. The audit therefore uses three explicit coverage layers:

1. **Inventory coverage** — every discoverable constructor argument, catalog default and orchestration argument receives a row.
2. **Quick runtime coverage** — one maximal-safe short lifecycle run per model.
3. **OAT runtime coverage** — one-at-a-time mutation for every argument with a known bounded smoke value.

Arguments whose domains or interactions cannot be changed safely are still listed as `smoke_eligible=false`; they are not silently treated as verified.

## Lifecycle checks

For trainable models the execution authority must verify:

- construction and resolved configuration;
- short fit;
- prediction and output validation;
- model save and SHA-256 evidence;
- model load and prediction after load;
- equality/parity of prediction before and after load where deterministic;
- property inspection after fit/load;
- requested vs constructor vs effective argument evidence;
- retraining on the expanded smoke dataset;
- prediction after retraining.

For zero-shot models, fit/retrain are `NOT_APPLICABLE`; loading, prediction, revision/config evidence and output validation remain required.

## Outputs

- `matrix/model_argument_inventory.csv`
- `matrix/lifecycle_smoke_cases.csv`
- `matrix/lifecycle_smoke_cases.json`
- `matrix/audit_manifest.json`
- `runtime/` evidence from `all_model_runtime_validation.py`
- `final_audit_manifest.json`

## Profiles

```bash
PROFILE=quick AVAILABLE_ONLY=1 ./tools/run_all_model_argument_lifecycle_audit.sh
PROFILE=oat MODELS=extra-trees,lightgbm-classifier ./tools/run_all_model_argument_lifecycle_audit.sh
```

`quick` is the default for short verification. `oat` can be substantially longer.
