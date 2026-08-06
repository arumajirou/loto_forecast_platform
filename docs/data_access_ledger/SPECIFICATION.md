# Specification

## Core vocabulary

`DataRole`: RAW, TRAIN, VALIDATION, HOLDOUT, PROSPECTIVE_FEATURES,
PROSPECTIVE_PREDICTIONS, ACTUALS, METADATA.

`AccessOperation`: READ, FIT_MODEL, FIT_SCALER, FIT_ENCODER, SELECT_FEATURES, TUNE,
TRANSFORM, CALIBRATE, PREDICT, LOCK_PREDICTION, READ_ACTUALS, SCORE, REGISTER, PROMOTE.

`Stage`: TRAIN, VALIDATION, OOF, HOLDOUT, PROSPECTIVE, SCORING, REGISTRATION, PROMOTION.

`AccessDecision`: PASS, BLOCKED, INVALID, NOT_APPLICABLE.

## Validation semantics

- Structural or tamper failures return `INVALID`.
- Leakage or chronology failures return `BLOCKED` when no structural invalidity is present.
- Warnings, including missing expected OOF seeds, do not independently prevent `PASS`.
- Any error prevents `PASS`.
- `actuals_known` remains an operator assertion and is never sufficient evidence for actual access.
- `notes` are descriptive only and are never consulted by the validator.

## Fit and tuning

FIT_MODEL, FIT_SCALER, FIT_ENCODER, and SELECT_FEATURES require one or more TRAIN slices and
reject any
other role. TUNE requires TRAIN-role outer data whose inner fold partitions are explicitly
marked and
chronological. Its HPO_RESULT state must include the exact canonical fold hash.

## OOF

OOF events require fold ID and seed. The corresponding model fit must precede prediction for the
same
fold and seed. Fit/calibration/feature-selection cannot consume a validation fold. The final Train
observed timestamp must be strictly earlier than the Validation observed start. Expected but absent
seed predictions are warnings; differing training ranges across seeds are errors.

## Holdout and Prospective

Holdout cannot participate in fit, scaler fit, encoder fit, feature selection, or tuning. Holdout
actual reads require an earlier Holdout prediction. Prospective scoring follows `PREDICT`,
`LOCK_PREDICTION`, `READ_ACTUALS`, `SCORE`; actual-bearing slices or states cannot be used for
prediction.
Actual draw identity must match the event forecast identity.
