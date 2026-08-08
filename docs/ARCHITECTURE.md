# Architecture

## Status

`CURRENT`

This document describes the repository-wide architectural contract. Feature-specific documents may add stricter requirements, but they must not silently weaken the constraints below.

## 1. Goals

The platform prioritizes reproducible time-series research, leakage-resistant evaluation, immutable prospective prediction evidence, provider/model exchangeability, operational auditability, and portability across supported development environments.

A model being listed as available is not sufficient evidence of runtime success. Formal runtime evidence must distinguish catalog availability from verified loading and inference.

## 2. Forecasting and evaluation contract

The primary forecasting metric is **Hit@±1**: the fraction of predictions whose absolute error is at most 1.

Required companion metrics are:

- MAE;
- MSE;
- RMSE;
- per-position Hit@±1;
- all-position/row Hit@±1;
- dispersion across folds/seeds where applicable.

Set-overlap metrics such as Hits@k may be reported for select-family games, but they do not replace Hit@±1 as the primary positional forecasting metric.

Every serious comparison must include appropriate baselines such as Random, fixed value, mean, median, most-recent value, frequency-based methods, and statistical models when applicable.

The game-agnostic implementation in `src/loto/evaluation/metrics_general.py` derives positional dimensions from `GameGeometry` and supports MAE/MSE/RMSE together with element, row, and per-position tolerance metrics.

## 3. Time ordering and leakage boundary

Research data is divided in time order. The repository uses staged development/evaluation paths including validation/OOF, Holdout, and Prospective phases.

The architectural rules are:

- training precedes validation/OOF;
- Holdout is not used for candidate tuning;
- Prospective predictions are created before their actual outcomes are known;
- scalers, encoders, feature selection, and hyperparameter search are fitted or selected only from data available to the permitted training/development boundary;
- future information, order violations, duplicates, and missing-value handling are explicitly audited rather than silently repaired across time boundaries.

`src/loto/auto_campaign/contracts.py` exposes separate OOF, Holdout, and Prospective campaign stages. `src/loto/evaluation/splits.py` implements chronological rolling/development-holdout split primitives.

## 4. Data governance

Raw source data is an immutable evidence layer. A correction creates a new data/versioned artifact rather than overwriting the previous raw source in place.

Time-aware data contracts distinguish event/draw time from availability time. External variables whose availability cannot be established for the prediction timestamp are not eligible for formal leakage-safe use.

Current data-contract details are indexed from [DATA_CONTRACTS.md](DATA_CONTRACTS.md) and feature-specific governance documents.

## 5. Forecast tracks and model comparison

The architecture supports comparison of multiple forecasting approaches under the same evaluation protocol, including:

- univariate models;
- models with eligible exogenous variables;
- per-position models;
- shared/joint models where the experiment contract permits them;
- ensembles;
- statistical, machine-learning, deep-learning, and time-series foundation-model adapters.

Promotion is evidence-driven. Selecting only the single best random seed without reporting multi-seed behavior is not an acceptable adoption rule.

## 6. Prediction locking

Prospective prediction values are fixed before actual outcomes are introduced.

The prediction-lock path binds prospective outputs to configuration/data/lineage evidence and SHA-256 records. Lock evidence includes a timestamp and verifies that actual-bearing artifacts were not present at lock time.

`src/loto/auto_campaign/prediction_lock.py` implements campaign-level prediction locking and verification. Portable-bundle verification re-evaluates the embedded lock after relocation.

A prediction lock proves integrity/order properties of the recorded artifact. It does not prove forecast accuracy.

## 7. Runtime certification

Runtime certification is provider-neutral and separate from model catalog availability.

A formal success claim requires evidence for the relevant execution path, including as applicable:

- model/package/revision identity;
- load success;
- input acceptance;
- inference execution;
- output shape/contract;
- finite output values;
- device evidence;
- GPU process/device/VRAM evidence for GPU-certified runs;
- explicit CPU fallback status.

`src/loto/runtime_certification/` provides the provider-neutral certification SDK foundation. Provider-specific adapters may add stricter checks.

Unavailable or unexecuted runtime checks must not be represented as PASS.

## 8. Reproducibility and run evidence

Experiments should be bound to stable identities and hashes such as Run ID, resolved configuration, data hash/snapshot, code hash/Git commit, model ID/revision, seed, predictions, actuals, metrics, runtime logs, and device information.

OOF and multi-seed evidence should retain aggregate behavior, dispersion, and adverse/worst observations rather than only the best trial.

Persistence backends may include files/Parquet and operational stores such as PostgreSQL, DuckDB, or MLflow depending on the workflow. Storage availability does not change the evidence contract.

## 9. Building blocks

The repository is a modular Python platform whose responsibilities include, among others:

```text
data / provenance             acquisition, canonicalization, availability and lineage
features                      as-of feature generation
models / provider adapters    baselines and forecasting implementations
evaluation                    metrics, splits, uncertainty and promotion evidence
auto_campaign                 staged search/OOF/Holdout/Prospective workflows
sealing / prediction lock     immutable prospective evidence
registry / persistence        artifact and operational records
runtime_certification         verified load/inference evidence
telemetry / observability     metrics, traces and runtime evidence
orchestration                 end-to-end workflow coordination
api                           service boundary
```

Directory-name symmetry with documentation is not required; semantic ownership is documented instead.

## 10. Portability and deployment

Windows and Linux are explicit engineering/verification targets for portable repository operations. Filesystem paths, subprocess execution, line endings, temporary directories, case sensitivity, optional GPU stacks, and shell assumptions must be treated as portability concerns.

Production or hardware certification can remain environment-specific, but a platform document must not treat successful execution on one OS/device as proof for another.

Environment-specific service managers such as systemd belong to deployment adapters rather than the cross-platform core contract.

## 11. Safety and promotion

The platform fails closed on evidence that can invalidate scientific or operational claims, including future-data leakage, destructive Raw mutation, invalid prediction-lock evidence, non-finite inference output, or missing mandatory runtime identity.

Holdout/Prospective access, production binding, promotion, and irreversible migrations are separate controlled operations. Documentation changes do not authorize any of them.

## 12. Documentation authority

Current repository-wide documentation is governed by [DOCUMENTATION_CONTRACT.md](DOCUMENTATION_CONTRACT.md).

Dated verification/design snapshots are preserved as historical evidence. Their old test counts, model counts, merge state, hardware assumptions, or implementation status must not be silently promoted to current platform claims.
