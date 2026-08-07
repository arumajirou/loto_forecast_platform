# Darts OOF, multi-seed, and provenance contract

**Status:** `LOCAL_CONTRACT_VERIFIED / REAL_DARTS_RUNTIME_PENDING`

## Temporal folds

OOF uses expanding chronological windows. Training always starts at the first supplied row.
Validation starts exactly where training ends, so folds are adjacent, ordered, and non-overlapping.
Scaler, encoder, feature selection, and tuning state must be fitted inside each training slice only.
The generic OOF runner passes deep copies to evaluators and verifies that the source frame was not
mutated.

## Multiple seeds

A candidate requires at least two unique seeds, and every seed must cover the same fold IDs. Metrics
are averaged over folds inside each seed first. The retained seed summaries are then aggregated into
mean, population variance, and worst value. For Hit@±1, worst means minimum. For MAE, MSE, and RMSE,
worst means maximum. Position-wise Hit@±1 summaries are retained using the same rule.

Selection never uses the best seed alone. Ranking is based on mean Hit@±1, then worst-seed Hit@±1,
then all-position Hit@±1, then MAE. A candidate is only proposed as champion when mean Hit@±1 beats
the declared baseline and worst-seed Hit@±1 does not regress.

## Baselines

Model candidates and Random, fixed, mean, median, last, frequency, seasonal, and statistical
baselines must use identical folds and seed sets. A mismatched comparison fails closed.
A run with no candidate passing the primary baseline gate records `NO_CHAMPION` rather
than selecting the least-bad model.

## Provenance

Each run record includes Run ID, UTC time, immutable data/config/code SHA-256 values, Git commit,
model ID, model revision, and every seed. Data hashes include column order, dtypes,
and serialized values. Code hashes include sorted path names and bytes. A changed value,
configuration, or source file produces a different digest.

## Certification boundary

Unit tests validate fold construction, source immutability, seed/fold coverage, aggregation, stable
candidate selection, baseline gating, and tamper-sensitive provenance hashes. They do not certify
Darts 0.46.1 imports, real model fitting, real OOF accuracy, Torch, CUDA, GPU PID, VRAM, or CPU
fallback.
