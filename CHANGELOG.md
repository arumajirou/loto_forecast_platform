# Changelog

All notable platform changes are recorded here. Current package version values are not duplicated in
this file; release headings are historical records.

## Unreleased

### Changed

- Established `loto.version.__version__` as the single application-version source.
- Derived setuptools package metadata from the canonical Python attribute.
- Made FastAPI metadata, dashboard text, console scripts, and integrity-release defaults consume the canonical version.
- Removed the mutable current-version string from the README title.
- Updated the validated GitHub Actions checkout pin to actions/checkout v7.0.1 through PR #244.
- Updated the `full` dependency lane to Ray Tune `>=2.56.1` and refreshed `uv.lock` through PR #242.
- Updated FastAPI to `>=0.141.1,<0.142` with a refreshed lock through PR #243 after exact-head Linux and native Windows verification.
- Updated the routine dependency group through PR #241: Uvicorn 0.52.1 lane, MLflow 3.15.1 lane, Hypothesis 6.165.2 lane, Ruff 0.16.1 lane, and GluonTS 0.17.0 lane, with a refreshed universal lock.
- Refreshed current repository status, handoff, verification, runbook and documentation authority guidance after the merge batch.

### Added

- Added atomic `BUILD_INFO.json` generation with separate package version, schema version, Git commit, Git dirty state, explicit build time, and generation time fields.
- Added fail-safe source-only behavior when installed package metadata is unavailable.
- Added version-consistency, dashboard, CLI, package-metadata, BUILD_INFO, and README tests.
- Added `VERSION_DESIGN.md` and the historical root `VERIFICATION_REPORT.md` documentation.
- Added the merged `uv run loto3 campaign` all-model × all-six-game development evaluation surface through PR #248, including fail-visible coverage rows, Hit@±1-first metrics, mandatory baselines, complete seed summaries and prediction sealing.
- Added the explicit `MAP` / `WITHIN_TAU` constrained select-game decoder objective through PR #249 while preserving the historical MAP compatibility API.
- Added `docs/CURRENT_HANDOFF.md`, `docs/CURRENT_VERIFICATION_REPORT.md`, `docs/CURRENT_RUNBOOK.md`, and `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` as current-state entry points while retaining older reports as historical evidence.
