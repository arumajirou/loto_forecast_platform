# Changelog

All notable platform changes are recorded here. Current package version values are not duplicated in this file; release headings are historical records.

## Unreleased

### Changed

- Established `loto.version.__version__` as the single application-version source and derived package/runtime metadata from it.
- Updated the routine dependency and tooling lanes, including Ray Tune, FastAPI/Uvicorn, MLflow, Ruff and GluonTS, while retaining `uv.lock` as the committed lock authority.
- Routed probability-bearing unified-campaign candidate estimators through family-specific Hit@±1/WITHIN_TAU decoding while keeping point-only workers point-only.
- Generalized outcome metrics across all six canonical game geometries, including exact positional semantics for Numbers3/Numbers4.
- Added theory-aware Hit@±1 promotion semantics while preserving historical evidence schemas and manual-only promotion safeguards.
- Added paired-score MDE/power planning for pre-experiment detectability checks.
- Added statistical dependence/trend/change-point utilities plus guarded causal DAG/event-study/negative-control foundations in PR #268.
- Repaired runtime evidence serialization and introduced a resource-aware broad execution path in PR #270.
- Stabilized the scheduler in PR #277 with deterministic resume fingerprints, physical GPU assignment, process-tree timeout cleanup and a strict outer worker cap.
- Reorganized current documentation around code-grounded library/model compatibility rather than treating catalog registration as execution success.
- Added and then refreshed the root README/current-state documents through PRs #299, #300 and #308.
- Added `loto-sklearn`, a dynamic all-estimator scikit-learn discovery/smoke/certification surface in PR #301 without changing Broad v1=174.
- Added process-parallel six-game Unified Campaign execution, CPU affinity/thread controls, live `progress.json` status and aggregate artifacts in PR #302.
- Completed the Broad isotonic calibrated logistic factory/routing path in PR #303.
- Routed scheduler GPU leases into XGBoost and CatBoost constructors and verified real GPU activity on the exact PR source in PR #304.
- Added a fail-closed LightGBM accelerator probe in PR #305; the resolved LightGBM 4.7.0 build does not support the CUDA tree learner but its OpenCL `device_type="gpu"` backend was verified.
- Routed LightGBM candidate/position workers through that verified OpenCL GPU contract in PR #306 without claiming CUDA support.
- Normalized the sktime P1 formal input contract to the provider's float representation and restored the four-model formal P1 verification path in PR #307.
- Added a current skforecast 0.23.0 operator-runtime evidence document. The evidence is deliberately classified separately from current-main repository routing/certification and does not close Expanded v2 #289 / TAJ-32.

### Added

- Added atomic `BUILD_INFO.json` generation with package version, schema version, Git commit/dirty state and timestamps.
- Added version-consistency, dashboard, CLI, package-metadata, BUILD_INFO and README tests.
- Added the merged `uv run loto3 campaign` all-model × all-six-game development evaluation surface, fail-visible coverage rows, Hit@±1-first metrics, mandatory baselines, complete seed summaries and prediction sealing.
- Added explicit MAP/WITHIN_TAU constrained select-game decoding.
- Added `docs/CURRENT_HANDOFF.md`, `docs/CURRENT_VERIFICATION_REPORT.md`, `docs/CURRENT_RUNBOOK.md`, `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` and `docs/CAPABILITIES_AND_OPERATIONS.md` as current-state entry points while retaining older reports as historical evidence.
- Added GitHub repository observability/operations documentation and Actions summary workflows in PR #273.
- Added an evidence-aware static visual dashboard and explicit GitHub Pages deployment gate in PR #274; public Pages activation remains separately gated.
- Added the GitHub operations control-center/documentation classification layer in PR #276.
- Added Expanded Inventory v2 foundation in PR #293 while preserving Broad v1 and Unified v1 denominators; AutoGluon expands from one umbrella to 29 source model identities + 8 unique ensemble identities.
- Added Toto 2.0 family manifest / 22M provenance foundation in PR #295 and the 22M runtime-certification infrastructure in PR #296. Formal 22M runtime certification remains separately blocked by the native-Linux external GPU process/release gate (#297).
- Added `docs/SKLEARN_ALL_MODELS.md`, `docs/PARALLEL_UNIFIED_CAMPAIGN.md` and `docs/LIGHTGBM_GPU_CERTIFICATION.md` for the new execution/runtime surfaces.
- Added `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` to record the 2026-08-13 operator-local skforecast 0.23.0 evidence, including core forecasters, RNN GPU/CPU fallback, Chronos-2, TimesFM 2.5, Moirai-2 compatibility override behavior, TabICL artifact verification and the current TabPFN-TS license/authentication block.

### Current evidence boundaries

- Broad v1 remains **174** and is not rewritten by dynamic or Expanded v2 inventories.
- Unified v1 remains **250** canonical identities / **1,500** planning units.
- Expanded v2 Phase 1 currently derives **210** implementation identities; later phases remain open.
- sktime registry discovery/importability is broader than the currently formally verified four-model P1 runtime matrix.
- skforecast operator-local runtime evidence is **not** equivalent to current-main Expanded v2 repository integration.
- Moirai-2 passed runtime only under a controlled unsupported dependency metadata override; normal dependency routability remains blocked.
- TabICL v2 operator runtime and checkpoint SHA-256 were verified.
- TabPFN-TS V3 inference is not certified; the current operator diagnosis found an invalid/expired Prior Labs token before checkpoint download/inference.
- Holdout remains **CLOSED**.
- Prospective remains **CLOSED**.
- Automatic promotion/retraining/registry write remains **FORBIDDEN**.
