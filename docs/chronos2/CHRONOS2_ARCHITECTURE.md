# Chronos-2 Architecture

```text
JSON Request
  -> schema-v1 adapter (optional)
  -> Pydantic Contract v2
  -> chronology + GameGeometry compiler
  -> synthetic regular timeline + covariate compiler
  -> isolated Chronos2Pipeline loader
  -> predict_df
  -> shape/finite/identity/quantile checks
  -> Parquet + manifest + SHA-256 artifacts
  -> JSON Response v2
```

The implementation is isolated under `src/loto/adapters/chronos2`, `src/loto/chronos2_campaign`, and `environments/chronos2-py313`. Shared workers, catalogs, root dependencies, workflows, and other Chronos variants are untouched.
