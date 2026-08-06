# Evaluation Plan

## Target layout

The default is one univariate model per game position for Numbers3, Numbers4,
MiniLoto, Loto6, and Loto7. A shared position-prefixed model is optional and must
be compared under the same data and budget. A joint-token model is not the
default because its alphabet can grow rapidly.

## Forecast horizons

- Horizon 1: future native exact one-step categorical prediction.
- Horizons 2 and 5: future project extensions using recursive prediction or seeded
  sampling without future actual updates.
- Draw sequence is the native ordering. Calendar time is metadata unless a later
  explicit feature contract is approved.

## Leakage prevention

Train, Validation, Holdout, and Prospective are chronological. Depth, beta,
priors, pruning, and any model selection are fit using Train only. A prediction
must be generated and SHA-256 sealed before the scored actual is supplied to the
update. Raw data is immutable.

## Metrics and baselines

Hit@±1 is primary. Also report MAE, MSE, RMSE, position-wise and all-position
Hit@±1, categorical accuracy, Brier score, ECE, log score, cumulative sequential
log loss, mean, variance, and worst seed. Compare Random, fixed, mean, median,
last value, frequency, Dirichlet categorical, fixed-depth n-gram, and statistical
baselines under identical chronological folds.

No best-seed-only promotion is allowed.
