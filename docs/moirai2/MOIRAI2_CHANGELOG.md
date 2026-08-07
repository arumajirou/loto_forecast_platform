# Moirai 2.0 Changelog

## 0.4.0

- Added a fail-closed reviewed-lock and frozen-runtime preflight.
- Added deterministic draw-sequence and calendar-time certification request factories.
- Added target-only, past-only, and past-plus-known-future runtime cases.
- Added a strictly serial six-case campaign runner that reuses the P8 two-process certifier.
- Added campaign-level all-case aggregation, immutable output directories, manifests, and hashes.
- Added explicit partial-run behavior that cannot grant formal runtime certification.
- Added P8A focused tests, change scope, test plan, verification report, and run configuration.

## 0.3.0

- Added a two-process pinned-snapshot runtime certification harness.
- Added canonical prediction and nine-quantile SHA-256 comparison.
- Added torch forward input/output tensor-device observation.
- Added external `nvidia-smi` PID, GPU UUID, VRAM, and post-exit PID-release evidence.
- Added immutable per-run request, response, logs, exit code, monitor samples, and manifests.
- Added strict failure gates for same PID, changed predictions, changed artifacts, and CPU fallback.
- Added P8 focused tests, change scope, test plan, verification report, and run configuration.

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
