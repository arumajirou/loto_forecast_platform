# Chronos-2 Verification Report

## Executed

- `python3 -m compileall -q src scripts tests`: PASS
- focused pytest for Chronos-2 adapters/campaign: 38 PASS
- schema-v1 adapter: PASS
- horizons 1/2/5: PASS
- game position counts 3/4/5/6/7/8: PASS
- local/panel/multivariate mock inference: PASS
- quantile crossing rejection: PASS
- non-finite rejection: PASS
- snapshot hash inventory: PASS with temporary fixtures

## Not executed

- actual `chronos-forecasting==2.3.1` model load
- CPU inference with real weights
- RTX 5070 Ti inference and GPU process correlation
- separate-process forecast equivalence with the real snapshot
- Ruff and mypy (tools unavailable in the authoring container)
- root full pytest and GitHub Actions

Overall status: `PARTIALLY_VERIFIED`.
