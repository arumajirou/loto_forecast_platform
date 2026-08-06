# Sundial provider v2 semantic verification

## Status

`SEMANTIC_VERIFIER_IMPLEMENTED / TARGET_HOST_EXECUTION_PENDING`

Formal certification now includes a verifier independent from the provider response contract.
It recomputes all summaries from the raw generated samples and checks the fixed snapshot before the
model is loaded.

## Snapshot pins

```text
revision=3212e42564493f520593e5414af4367fc4b49226
config.json=173dd40c0a7e08a71b660110fd6334ee85eb9f6ce6f30df0a6cbaea3bb1ff3b4
generation_config.json=d90f7f1d9ef012f9ec0bd76fdf42e6979d086f157d65910b3b273edfb100e748
model.safetensors=414435b508391f92afadd2aaeec418c806776aeccbce12e638d73a139ca5ca78
```

The remote-code files are checked against the existing approved review and the hashes recorded by
PR #14. An unexpected weight or runtime Python file fails the snapshot preflight.

## Output recomputation

For every CPU, CUDA, and replay case, the verifier recomputes:

- mean;
- median;
- population standard deviation;
- every declared empirical quantile;
- the selected legacy point forecast.

It also checks `point_forecasts`, quantile keys and levels, response properties, snapshot path,
artifact identity, and fixed config, weight, and remote-code hashes.

The final gate requires both semantic stages:

```text
semantic-snapshot-preflight
semantic-output-verification
```

A provider certification cannot become final-gate PASS when either semantic stage fails.
