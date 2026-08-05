# Moirai 2.0 Provider Protocol

Request schema: `2`. Response schema: `2`. Operations: `identity`, `predict`.
Formal model ID: `moirai-2.0-r-small`. Formal horizons: `1`, `2`, `5`.
Formal point method: `median_q0.5`. Native levels: `0.1` through `0.9`.

A CUDA request that cannot execute on CUDA returns a nonzero provider exit and error evidence.
The response retains `runtime_evidence`, `gpu_evidence`, `artifact_reference`, and
`license_evidence`. Provider metadata is a reference manifest, not serialized model weights.
