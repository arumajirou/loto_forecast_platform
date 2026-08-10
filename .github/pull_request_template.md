## Objective

<!-- What problem does this PR solve? Keep scientific claims separate from implementation claims. -->

## Scope

- 

## Evidence level

- [ ] PROPOSED only
- [ ] IMPLEMENTED / code-path verified
- [ ] RUNTIME_VERIFIED
- [ ] OOF_EVALUATED
- [ ] HOLDOUT_EVALUATED
- [ ] PROSPECTIVE_EVALUATED

`champion=null` / `NO_MODEL_BEATS_BASELINE` are valid outcomes.

## Scientific protocol checklist

- [ ] Hit@±1 is the primary forecast metric where forecast quality is evaluated.
- [ ] MAE, MSE, RMSE, position Hit@±1 and all-position Hit@±1 are retained where applicable.
- [ ] Random, fixed, mean, median, last, frequency and statistical baselines use the same eligible folds.
- [ ] Scaler/encoder/feature selection/HPO/calibration are fit on Train/history only.
- [ ] All configured seeds are retained; best-seed-only selection is not used.
- [ ] Prediction bytes are sealed before corresponding actuals are read.
- [ ] Holdout/Prospective access is unchanged unless this PR is explicitly an approved phase-unseal change.
- [ ] Runtime availability is not presented as forecast accuracy evidence.

## Data / integrity

- [ ] Raw data and historical evidence are not overwritten.
- [ ] New result-affecting artifacts record data/code/config/protocol identity.
- [ ] SHA256SUMS / artifact manifests were verified when touched.
- [ ] No secrets or workstation-specific credentials are introduced.

## Documentation review checklist

When documentation/status claims change:

- [ ] re-fetch default branch/head and relevant PR/Issue state;
- [ ] compare generated counts with their generator/source;
- [ ] verify cited paths exist;
- [ ] label fixed SHA/run/count values as stable contract or point-in-time evidence;
- [ ] avoid unqualified `latest/current` wording for volatile facts;
- [ ] preserve historical evidence instead of silently rewriting it;
- [ ] confirm scientific status is not promoted beyond executed evidence.

## Verification

```text
BASE_SHA=
HEAD_SHA=
FOCUSED_TESTS=
SMOKE=
RUFF=
MYPY=
FULL_PYTEST=
CI=
HOLDOUT_OPENED=false
PROSPECTIVE_OPENED=false
```

## Merge safety

- [ ] exact changed-file list reviewed;
- [ ] unresolved review threads = 0;
- [ ] latest base/race state re-fetched;
- [ ] expected-head merge guard used when available.
