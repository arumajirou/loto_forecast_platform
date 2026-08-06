# Test Plan

## Contract tests

Unknown fields, bool/int confusion, naive datetime, non-UTC offset, uppercase SHA, invalid
actual role,
serialize/deserialize, and explicit non-claim statements.

## Fit and state tests

Train-only model/scaler fit, Validation scaler fit rejection, Holdout model fit rejection,
Train-fitted
Validation transform, state used before fit, state hash mismatch, and fitted dataset mismatch.

## Chronology and OOF tests

Sequence gap, timestamp reversal, missing parent, parent cycle, duplicate event ID,
chronological OOF,
OOF target-fold fit rejection, future-fold calibration rejection, chronological tuning fold hash,
non-Train tuning rejection, and missing expected seed warning.

## Prospective and tamper tests

Prediction-lock-actual-score PASS, actual read before prediction/lock, score before actual read,
future
availability, draw identity mismatch, canonical dictionary ordering, event-order hash sensitivity,
ledger tamper, NaN/Inf, set, and bytes rejection.

## CLI tests

Exit 0 for PASS, exit 1 for schema INVALID/BLOCKED, and exit 2 for malformed JSON or
environment/input
failure.
