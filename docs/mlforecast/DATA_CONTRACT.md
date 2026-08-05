# MLForecast data contract

## Canonical panel

Required columns:

| Column | Type | Meaning |
|---|---|---|
| `unique_id` | string-compatible | Series or position identifier |
| `ds` | sortable integer, datetime, or timestamp-compatible | Observation time or draw order |
| `y` | finite numeric | Target value |

The pair `(unique_id, ds)` must be unique. Rows must already be ordered by `unique_id` and `ds`; the system does not silently reorder invalid input before validation.

## Optional feature roles

Every additional input column must belong to exactly one declared role:

| Role | Rules |
|---|---|
| `static_features` | Constant within each `unique_id`; must not overlap other roles |
| `known_future_features` | Available for every required Holdout or Prospective key before prediction |
| `weight_col` | Finite, non-negative numeric sample weight |

Unclassified columns fail closed. `static_features=[]` is explicit and prevents MLForecast from treating all additional columns as static by default.

## Missing and finite-value policy

- `unique_id`, `ds`, and `y` must not be missing.
- Target values must be finite.
- Declared static, known-future, and weight columns must exist.
- Required known-future values must not be missing.
- Weight values must be finite and non-negative.
- Model output values must be finite.

## Time partitioning

Partitions are ordered and non-overlapping:

```text
Train -> Validation -> Holdout -> Prospective
```

All transformations, feature selection, model fitting, and hyperparameter search are trained inside Train. Validation and Holdout cannot influence fitted state. Prospective predictions are produced and sealed before actual values are attached.

## Future exogenous contract

Future data must contain exactly:

```text
unique_id, ds, <declared known_future_features>
```

The key set must exactly equal `MLForecast.make_future_dataframe(h)` for the requested horizon. Missing keys, extra keys, duplicate keys, missing feature columns, and undeclared columns are rejected.

Static columns are not passed through future `X_df`; they are learned from historical rows and declared through `static_features`.

## Position semantics

For multi-position lottery targets, each position is represented as a separate `unique_id`. Position-wise metrics are grouped by this identifier. All-position Hit@±1 requires every position for the same draw/time key to be within absolute error 1.

## Raw-data integrity

When execution begins from a file, the raw source is copied into the run artifact directory. It is not overwritten. Canonicalized panel, Train, Holdout, configuration, predictions, metrics, model bundles, manifests, and sums are stored separately.

## Prediction seal

Before actual values are known, prospective predictions are serialized, timestamped in UTC, hashed with SHA-256, and recorded with `actual_known=false`. Any later comparison must reference the sealed prediction hash.
