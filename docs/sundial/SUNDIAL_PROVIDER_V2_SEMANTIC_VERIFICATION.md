# Sundial provider v2 semantic verification

## Status

`SEMANTIC_VERIFIER_IMPLEMENTED / EVIDENCE_ARCHIVE_WIRED / TARGET_HOST_EXECUTION_PENDING`

Formal certification includes a verifier independent from the provider response contract. It
recomputes all summaries from the raw generated samples and checks the fixed snapshot before the
model is loaded.

## Snapshot pins

```text
revision=3212e42564493f520593e5414af4367fc4b49226
config.json=173dd40c0a7e08a71b660110fd6334ee85eb9f6ce6f30df0a6cbaea3bb1ff3b4
generation_config.json=d90f7f1d9ef012f9ec0bd76fdf42e6979d086f157d65910b3b273edfb100e748
model.safetensors=414435b508391f92afadd2aaeec418c806776aeccbce12e638d73a139ca5ca78
```

The remote-code files are checked against the existing approved review and the hashes recorded by
the pinned snapshot probe. Unexpected Python or weight files fail verification.

## Response recomputation

For each of the eight certification cases, the verifier recomputes from raw samples:

- mean;
- median;
- population standard deviation;
- every declared empirical quantile;
- selected mean or median point prediction.

It then compares the recomputed values with `sample_statistics`, `point_forecasts`, `quantiles`,
and `predictions`, while also validating identity, shape, finite values, and snapshot properties.

## Evidence handoff

A successful run writes:

```text
artifacts/sundial-provider-v2-semantic-verification/<RUN_ID>.json
```

The evidence verifier receives this path with `--semantic-report`, records its SHA-256, and embeds
it inside the shareable evidence ZIP as:

```text
semantic/<RUN_ID>.json
```

Both the package launcher and final gate reopen the ZIP and require this entry before they can
complete successfully.

## Formal result

`SUNDIAL_PROVIDER_V2_SEMANTIC_VERIFICATION=PASS` is required alongside certification, evidence
verification, and final-gate PASS. Target-host execution remains pending.
