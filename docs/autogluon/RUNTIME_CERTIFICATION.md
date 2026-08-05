# AutoGluon TimeSeries P5 Runtime Certification

Status: IMPLEMENTED_HARNESS / real AutoGluon execution required

## Certification boundary

A model is not certified merely because it appears in the runtime registry. P5 requires
an isolated AutoGluon 1.5.0 process to validate request loading, model construction,
training, prediction, output shape, finite values, quantiles, persistence, reload,
provider PID, resolved device, and an intentional CUDA-to-CPU fallback case.

The default campaign runs seven scenarios:

1. explicit `Naive` fit/predict/save;
2. `Naive` load/predict from the saved artifact;
3. explicit `Theta` fit/predict/save;
4. the `fast_training` preset;
5. explicit `Naive` + `Theta` multi-model training with ensemble enabled;
6. bounded two-trial HPO for `SeasonalNaive`;
7. a CUDA request with `CUDA_VISIBLE_DEVICES` intentionally empty to prove CPU fallback.

The HPO request uses JSON-safe search-space descriptors. The provider converts these to
`autogluon.common.space.Categorical`, `Int`, or `Real` only inside the isolated runtime.
Unknown descriptors, invalid bounds, and search spaces in non-HPO modes fail closed.
HPO without a custom search space remains accepted for backward compatibility but is not
used by the bounded P5 certification scenario.

## Run

```bash
RUN_ID="$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/autogluon/runtime-certification/${RUN_ID}"

PYTHONPATH=src uv run python -m loto.autogluon_campaign.runtime_certification \
  --repo-root "$PWD" \
  --output-dir "$OUT"
```

Exit codes are `0=VERIFIED`, `1=PARTIALLY_VERIFIED`, `2=BLOCKED_RUNTIME`, and `3=FAILED`.
Every request, response, stdout, stderr, scenario verdict, provider runtime evidence,
and report is retained. `RUNTIME_CERTIFICATION_REPORT.json` has a canonical SHA-256,
and `SHA256SUMS` covers the complete output directory.

## Current execution limitation

The implementation environment used to add this harness could not resolve external DNS,
so Python 3.12 and `autogluon.timeseries==1.5.0` could not be downloaded. Consequently,
real runtime and GPU certification remain `EXECUTION_PENDING`; this is not recorded as a
successful model run.
