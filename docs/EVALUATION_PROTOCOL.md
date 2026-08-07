# Evaluation Protocol

## Status

`CURRENT`

This document defines the repository-wide evaluation order and metric priority. Feature-specific experiments may add stricter gates, but they must not weaken these rules.

## 1. Time-ordered partitions

Use chronological partitions. The conceptual order is:

```text
Train -> Validation/OOF -> Holdout -> Prospective
```

- Train/development data is the only source for fitting scalers, encoders, feature-selection logic, and hyperparameter search.
- Validation/OOF is used for development-time comparison and uncertainty estimation.
- Holdout is not used for candidate tuning.
- Prospective predictions are produced and locked before their actual outcomes are introduced.
- Any modification made after Holdout inspection creates a new experiment generation; the previous Holdout result must not be reused as if it were untouched.

## 2. Primary metric

The highest-priority forecasting metric is **Hit@±1**:

```text
abs(predicted - actual) <= 1
```

Required reporting includes:

- pooled/element Hit@±1;
- per-position Hit@±1;
- all-position/row Hit@±1;
- MAE;
- MSE;
- RMSE.

Where multiple folds or seeds are used, also retain aggregate behavior, dispersion, and adverse/worst observations. Do not adopt a model solely because one seed is the best observed seed.

Set-overlap Hits@k may be reported for select-family games, but it is a secondary metric and is not interchangeable with positional Hit@±1.

## 3. Baseline comparison

A candidate is interpreted relative to relevant baselines. The comparison set should include, when applicable:

- Random;
- fixed-value prediction;
- historical mean;
- historical median;
- most-recent value;
- frequency-based prediction;
- statistical forecasting models.

A model is not a champion merely because it is the best member of a weak candidate set.

## 4. Model-family fairness

Compare eligible approaches under the same data boundary, horizon, metric implementation, and evaluation windows. This includes, as applicable:

- univariate models;
- eligible exogenous-variable models;
- per-position models;
- shared/joint models;
- ensembles.

Changing the data boundary or metric definition changes the protocol and must not be treated as a directly comparable result without explicit reconciliation.

## 5. Leakage and order checks

Before promotion or a formal scientific claim, inspect at minimum:

- chronological ordering;
- duplicate observations/artifacts;
- missing-data handling;
- availability timestamps for exogenous data;
- future-information contamination;
- train/validation/holdout/prospective boundary violations.

Negative controls and lineage/data-access evidence should be used where the workflow supports them. Passing such checks is evidence against detected leakage, not proof that leakage is impossible.

## 6. OOF and multi-seed evidence

Store out-of-fold results and multi-seed evidence rather than only a single aggregate score. Formal evidence should make it possible to recover:

- fold/seed identity;
- metric values;
- mean/aggregate behavior;
- dispersion/variance where defined;
- worst/adverse observation used by the adoption gate.

Search-system randomness and final model randomness must not be silently conflated.

## 7. Prediction locking

Prospective predictions must be fixed before actual outcomes become available. The formal lock is recorded with SHA-256 evidence and a timestamp, together with the relevant configuration/data/lineage identities.

A lock verifies integrity and ordering of the prediction artifact; it does not imply predictive skill.

## 8. Statistical interpretation

- Bootstrap/resampling units must respect the draw/time-series dependence structure; positions must not be flattened into falsely independent samples for a test that assumes independence.
- Failure to reject a null hypothesis is not proof of uniformity or proof that a theoretical optimum has been reached.
- Multiple candidate comparisons require an appropriate multiplicity policy before significance claims are used for promotion.
- A champion may legitimately be `null` when no candidate clears the baseline/evidence gate.

## 9. Current implementation references

- `src/loto/evaluation/metrics_general.py` provides game-geometry-driven positional MAE/MSE/RMSE and tolerance metrics, including element, row, and per-position within-1 reporting.
- `src/loto/evaluation/splits.py` provides chronological rolling and development/Holdout split primitives.
- `src/loto/auto_campaign/contracts.py` separates OOF, Holdout, and Prospective campaign stages and supports multiple model seeds.
- `src/loto/auto_campaign/prediction_lock.py` provides prospective prediction-lock generation and verification.

Feature-specific verification reports may describe which parts of this protocol were actually executed for a particular run. Unexecuted checks must not be represented as PASS.
