# Timer-S1 data contract

Each history row contains a timezone-aware timestamp, one finite value per game position, and the
literal `future_actual=false`. Rows must be strictly increasing and unique. The provider selects the
last `context_length` rows and transposes them into independent position series.

The calendar mapping is serialized canonically and SHA-256 hashed. A verified response must bind
its chronology row count to `context_length`, report duplicate-free strict ordering, and preserve
`actuals_used=false`.

A verified success response is limited to `VERIFIED_CPU` or `VERIFIED_GPU` and requires a concrete
package version rather than an empty or unresolved sentinel. Input, native output, and normalized
output shapes are derived from the selected game, context length, nine fixed
quantiles, and prediction length. Every point and quantile value must be finite. Quantiles must be
monotone at every series/horizon cell, and the point forecast must equal q0.5.

CPU certification requires a requested and effective CPU device and forbids GPU evidence. GPU
certification requires a requested and effective CUDA device, no CPU fallback, GPU UUID, and
consistent before/peak/after process VRAM evidence.

Formal provenance binds request `config_sha256` to `config.json`,
`weight_manifest_sha256` to `model.safetensors.index.json`, and `weight_sha256` to the canonical
`timer-s1-weight-set-v1` digest over all required weight shard paths, sizes, and SHA-256 values.
The manifest must contain every canonical Timer-S1 core config, weight-index, four weight shards,
and three remote-code files with their required flags and kinds intact. Snapshot validation requires
exact manifest file accounting, regular non-symlink files, matching sizes and hashes, the exact
remote Python allowlist, an approved timezone-aware review, explicit denial of environment-secret
collection, telemetry/exfiltration, and unsafe deserialization, and offline environment variables.

No raw row is modified. No Holdout or Prospective actual is opened. Prediction locking is deferred
to the later evaluation phase after runtime certification.
