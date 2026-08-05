# All-AutoModel Accuracy Upgrade

## Objective

The primary metric is Hit@±1. Holdout and Prospective data are never used to
fit selection, calibration, ensemble membership, ensemble method, or decoder
parameters.

## Stages

1. Run every discovered NeuralForecast AutoModel through HPO and Validation
   replay.
2. Select promoted task signatures independently for P1 through P5 from
   Validation-only predictions. Constant or near-constant prediction collapse
   is penalized.
3. Run dense Train-only OOF for promoted candidates with multiple seeds.
4. Fit position-specific robust residual calibration by fold cross-fitting.
5. Build a greedy diverse ensemble independently for each position.
6. Learn an empirical Hit@±1 decoder from OOF residuals and enable it only when
   fold-cross-fitted OOF metrics improve.
7. Apply the frozen policy once to Holdout and later to Prospective predictions.

## Leakage controls

- Promotion uses only the Validation partition.
- Calibration and ensembles use only Train-partition OOF predictions.
- Decoder residual samples are fitted from OOF predictions.
- Holdout is evaluated once and cannot alter the policy.
- Prospective predictions are frozen with SHA-256 before actual values are known.

## Baselines

Baseline, fixed, random, mean, median, last-value, frequency and statistical
baseline models are excluded from execution, rankings and formal completion
counts. Historical baseline artifacts remain immutable audit evidence only.

## Accuracy claims

This upgrade is designed to improve model selection and reduce prediction
collapse. It does not guarantee higher out-of-sample accuracy. Formal success
requires higher Holdout Hit@±1 under the unchanged time split, together with
reported MAE, MSE, RMSE, per-position Hit@±1 and all-position Hit@±1.
