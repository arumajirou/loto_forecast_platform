# Timer-S1 data contract

Each history row contains a timezone-aware timestamp, one finite value per game position, and the
literal `future_actual=false`. Rows must be strictly increasing and unique. The provider selects the
last `context_length` rows and transposes them into independent position series.

The calendar mapping is serialized canonically and SHA-256 hashed. No raw row is modified. No
Holdout or Prospective actual is opened. Prediction locking is deferred to PR-D.
