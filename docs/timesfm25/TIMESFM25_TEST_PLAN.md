# TimesFM 2.5 Test Plan

Provider-contract tests cover package/checkpoint provenance, backend identity,
unknown-key rejection, GameGeometry, 3/4/5/6/7 series, horizons 1/2/5, full quantile
schema, finite values, monotonicity, point/q0.5 identity, post-processing
constraints, and v1 compatibility.

Runtime-bundle tests cover immutable Run IDs, atomic writes, CPU/GPU verdicts,
timeout and provider errors, SHA-256 sealing, missing and unexpected files, duplicate
entries, hash mismatch, and path escape detection.

Preflight tests cover successful pinned offline preparation, weight mismatch,
missing or malformed `uv.lock`, wrong locked versions, multiple weight files, CUDA
unavailability, offline variable enforcement, absolute snapshot paths, manifest
identity mismatch, and blocking provider execution after a failed preflight.

Pending execution tests are real target-host lock generation, model byte hashing,
GPU load/inference/PID/VRAM evidence, separate-process snapshot reload with real
weights, native/Transformers numeric parity, full pytest, and functional GitHub
Actions execution.
