# k-DPP fixed-cardinality private runtime

## Status

`PARTIALLY_VERIFIED / PR_B_IMPLEMENTED / FORMAL_CERTIFICATION_PENDING`

This stacked PR adds a private CPU runtime. It does not register
`pp-k-dpp-fixed-k` in the public catalog or native registry and does not expose
CLI, API, or TTS entry points.

## Runtime boundary

The runtime accepts only fixed-cardinality binary Train data. The chronology
range must exactly match the supplied rows, and the chronology feature hash
must match the Train indicators and optional item features. Prediction accepts
no actual values and requires `actuals_used=false`.

The default kernel is constructed as follows:

```text
quality_i = sqrt(smoothed historical count weight_i)
S_ij = exp(-||z_i - z_j||^2 / (2 gamma^2))
L = diag(quality) S diag(quality)
```

The default item features are Train-only co-occurrence profiles and frequencies.
An explicit item-feature matrix may be supplied, but it is included in the
chronology evidence hash.

`DIAGONAL_CONTROL` sets `S=I`. In that mode the k-DPP law is the Conditional
Bernoulli fixed-k law, and the state records
`DEGENERATE_TO_CONDITIONAL_BERNOULLI`.

## Reused mathematical foundation

The runtime calls the existing implementations and does not copy them:

- `prepare_kdpp` and `sample_kdpp` from `math/kdpp.py`
- PSD validation from `math/psd.py`
- elementary symmetric normalization from `math/elementary_symmetric.py`
- log-space DP from `math/logspace_dp.py`

Exact k-DPP inclusion marginals are computed from the prepared eigensystem using
`lambda_i e_(k-1)(lambda without i) / e_k(lambda)`.

## Persistence and replay

A saved state contains:

- `kdpp_state.json`
- `kdpp_state.npz`
- `artifact_manifest.json`
- `SHA256SUMS`

Load verifies the file inventory, file hashes, array hashes, state fingerprint,
PSD evidence, rank, normalizer, and kernel diagnostics. Prediction hashes omit
only the process-specific PID, allowing a separate process to prove deterministic
replay for the same state, request, and seed.

## Certification harness

`scripts/certify_kdpp_fixed_k_runtime.py` requires an external NPZ containing
`training_indicators` and optionally `item_features`. It has no synthetic-data
fallback. It writes request, response, state, runtime evidence, prediction lock,
and SHA-256 inventories.

The harness deliberately writes:

```text
formal_runtime_certification=false
```

until the dataset provenance and real historical cutoff are independently
reviewed. Running the harness is not an accuracy, promotion, or merge-readiness
claim.

## Non-claims

- no public catalog registration
- no native registry registration
- no OOF, Holdout, or Prospective evaluation
- no Hit@±1, MAE, MSE, or RMSE result
- no superiority over Conditional Bernoulli
- no GPU execution
- no formal runtime certification from synthetic fixtures
