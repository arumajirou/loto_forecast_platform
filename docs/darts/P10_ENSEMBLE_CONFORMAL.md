# P10 ensemble and conformal contract

## Scope

P10 retains four public Darts identities:

- `NaiveEnsembleModel`;
- `RegressionEnsembleModel`;
- `ConformalNaiveModel`;
- `ConformalQRModel`.

The phase is an evidence contract. It does not declare the real Darts runtime or any
accuracy improvement successful.

## Ensemble rules

`NaiveEnsembleModel` must reproduce the arithmetic mean of every declared base-model
prediction with identical position and horizon shapes. Missing, non-finite, or silently
omitted base predictions fail certification.

`RegressionEnsembleModel` must preserve every base-model identity for each seed, fold,
target and position. Stacking-training keys must be disjoint from evaluation keys and
must end before the evaluation partition. The `-1` training-window mode is accepted only
for pre-fitted global models when base-model retraining is disabled.

All base models must share `output_chunk_shift`. Likelihood-parameter ensembling requires
identical likelihood identities and quantile sets from every base model.

## Conformal rules

The underlying model must be a pre-trained global forecasting model. Train,
calibration, and evaluation ranges are chronological and non-overlapping. Requested
quantiles must be unique, strictly increasing, centered on `0.5`, and form symmetric
coverage pairs.

`ConformalQRModel` additionally requires probabilistic base-model evidence. Calibration
length and stride must produce the requested number of scores without using evaluation
rows.

Certification rejects:

- crossing quantiles;
- missing quantile outputs;
- lower bounds greater than upper bounds;
- conformal/base median drift when median parity is required;
- shape or finite-value failures;
- calibration/evaluation overlap.

For every interval, P10 stores nominal coverage, empirical coverage, coverage gap, mean
and median width, position-wise coverage, and all-position coverage.

## Reproducibility and failure retention

The campaign uses seeds `1`, `7`, and `19`, keeps outer worker capacity at eight, and
serializes GPU jobs. A model failure does not remove the model or stop the remaining
matrix. Configuration, model identity, stacking keys, evaluation keys, and prediction
payloads receive canonical SHA-256 values.
