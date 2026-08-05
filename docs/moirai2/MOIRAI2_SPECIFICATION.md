# Moirai 2.0 Specification

The provider boundary is Pydantic schema version 2 with unknown-field rejection. A request binds
one exact model identity, one research-only license lane, one `GameGeometry`, ordered series
identity, chronological history, time semantics, covariate contracts, context, formal horizon,
native quantiles, device, seed, and local-snapshot policy.

A successful response retains a horizon-by-position q0.5 matrix and nine horizon-by-position
quantile matrices. `samples` is always `null`; `num_samples=9` is forbidden because the model
emits nine quantile levels rather than nine samples.
