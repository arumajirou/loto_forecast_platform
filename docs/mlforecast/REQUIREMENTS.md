# MLForecast integration requirements

## Purpose

Provide a reproducible, leakage-safe MLForecast 1.1.0 integration for Core estimators and AutoMLForecast, with Hit@±1 as the primary evaluation objective and formal runtime and artifact certification.

## Functional requirements

1. Support Core and Auto execution as separate explicit modes.
2. Support the eight declared Core estimators and all eight official AutoModels.
3. Reject unknown model names, configuration keys, and unsupported API arguments.
4. Classify every non-key input column as static, known-future, or sample weight data.
5. Split Train, Validation, Holdout, and Prospective data in chronological order.
6. Fit scalers, encoders, transformations, feature selection, and hyperparameter search on Train only.
7. Optimize AutoML with Hit@±1 miss count first and bounded MAE only as a tie-breaker.
8. Report Hit@±1, position-wise Hit@±1, all-position Hit@±1, MAE, MSE, and RMSE.
9. Compare Random, fixed, mean, median, last-value, frequency, and seasonal-naive baselines under the same keys and windows.
10. Save, load, and re-predict before declaring a model runtime usable.
11. Seal Prospective predictions with UTC time and SHA-256 before actual values are known.
12. Preserve raw source data without overwrite and produce manifests and portable hashes.

## Runtime requirements

- Python execution uses `uv` and the repository `uv.lock` without modifying it.
- The installed MLForecast distribution must be exactly `1.1.0`.
- The official wheel must match SHA-256 `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748`.
- Core Ridge and AutoRidge smoke certification must produce finite outputs with expected shapes.
- Every requested AutoRidge Optuna trial must complete.
- Save/load predictions must preserve exact `(unique_id, ds)` keys and match numerically within `rtol=1e-8`, `atol=1e-8`.
- Certification is intentionally one process and one thread; formal campaigns use eight outer workers with inner-thread controls.

## Safety and integrity requirements

- Fail closed on duplicates, missing values, ordering violations, non-finite targets, invalid weights, future-key mismatch, unclassified features, and changing static values.
- Fail closed on wheel, version, metadata, model-load, output-shape, finite-value, and prediction-equality failures.
- Reject symlinks, unsafe paths, duplicate entries, checksum disagreement, and unexpected files in portable bundles.
- Do not claim accuracy improvement, baseline superiority, Prospective success, GPU success, or production persistence without matching execution evidence.

## Deliverables

The MLForecast scope must include:

- `README.md`
- `REQUIREMENTS.md`
- `SPECIFICATION.md`
- `ARCHITECTURE.md`
- `DATA_CONTRACT.md`
- `TEST_PLAN.md`
- `VERIFICATION_REPORT.md`
- `CHANGELOG.md`
- `HANDOFF.md`
- `RUNBOOK.md`
- runtime certification and bundle-verification instructions
- generated `ARTIFACT_MANIFEST.json` and `SHA256SUMS` in runtime and handoff ZIPs

## Acceptance gates

1. Focused tests pass with no unclassified failures.
2. Python compilation, AST parsing, shell syntax, and line-length checks pass.
3. Ruff format and lint pass when Ruff is available.
4. The exact installed-wheel runtime emits `RUNTIME_CERTIFIED`.
5. The portable evidence verifier emits `BUNDLE_VERIFIED`.
6. The source handoff verifier emits `HANDOFF_VERIFIED`.
7. A later formal multi-seed campaign reports mean, variance, and worst values and does not promote only the best seed.
