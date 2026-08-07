# Moirai 2.0 Changelog

## 0.2.0

- Wired past-only covariates to native `past_feat_dynamic_real`.
- Wired known-future covariates to native `feat_dynamic_real`.
- Added deterministic ordering, context slicing, calendar expansion, and SHA-256 evidence.
- Added covariate dimensions to the model token-budget calculation.
- Added adapter-side covariate identity and hash verification.
- Corrected univariate GluonTS input to one-dimensional target with `one_dim_target=true`.
- Added fake-boundary runner execution and focused regression tests.

## 0.1.0

- Added isolated supported and CUDA13-experimental runtime declarations.
- Added strict provider Contract v2 and schema-v1 compatibility conversion.
- Added dynamic game/time/token geometry and nine-quantile retention.
- Added package/model provenance and research-only license gates.
- Added focused tests and operator documentation.
