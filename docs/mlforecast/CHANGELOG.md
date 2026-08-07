# MLForecast changelog

## Unreleased

### Added

- Dedicated MLForecast Core and Auto configuration contracts.
- Eight Core estimators and all eight official AutoModels.
- Chronological Train/Holdout execution and leakage-safe future-feature validation.
- Hit@±1-first AutoML objective with bounded MAE tie-breaking.
- Baseline, aggregate, position-wise, and all-position metrics.
- Exact MLForecast 1.1.0 provenance and wheel SHA-256 contract.
- Core Ridge and AutoRidge runtime certifier.
- Save/load/re-predict key and numerical equality checks.
- Complete-trial requirement for AutoRidge certification.
- Deterministic runtime evidence ZIP and independent non-extracting verifier.
- ZIP-slip, symlink, device, encryption, checksum, member-count, and size-limit protections.
- Source handoff builder with required documents, source/config/test files, environment snapshots, manifest, sums, provenance, and deterministic ZIP.

### Fixed

- Corrected the initial mistaken assumption that MLForecast 1.1.0 was unavailable.
- Corrected runtime instructions so the verified local wheel is actually layered into the execution environment.
- Enforced single-thread certification instead of only recording thread variables.
- Added exact prediction-key equality after save/load.
- Rejected partial AutoRidge trial completion.
- Fixed source-run symlink checks that previously occurred after path resolution.
- Resolved repository root from script location instead of the caller's current Git repository.

### Boundaries

- Shared `pyproject.toml`, `uv.lock`, workflows, common CLI/catalog modules, and PR #43 remain unchanged.
- Installed official-wheel certification, real-data accuracy evaluation, formal multi-seed comparison, and production persistence remain pending.
