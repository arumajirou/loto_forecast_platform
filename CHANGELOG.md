# Changelog

All notable platform changes are recorded here. Current package version values are not duplicated in this file; release headings are historical records.

## Unreleased

### Changed

- Established `loto.version.__version__` as the single application-version source and derived package/runtime metadata from it.
- Updated routine dependency and tooling lanes while retaining repository-owned `uv.lock` files as lock authority.
- Routed probability-bearing candidates through family-specific Hit@±1/WITHIN_TAU decoding while keeping point-only workers point-only.
- Generalized outcome metrics across all six canonical game geometries, including exact positional semantics for Numbers3/Numbers4.
- Added theory-aware Hit@±1 promotion semantics while preserving historical evidence schemas and manual-only promotion safeguards.
- Added paired-score MDE/power planning for pre-experiment detectability checks.
- Added statistical dependence/trend/change-point utilities plus guarded causal DAG/event-study/negative-control foundations in PR #268.
- Repaired runtime evidence serialization and introduced a resource-aware broad execution path in PR #270.
- Stabilized the scheduler in PR #277 with deterministic resume fingerprints, physical GPU assignment, process-tree timeout cleanup and a strict outer worker cap.
- Reorganized current documentation around code-grounded library/model compatibility rather than treating catalog registration as execution success.
- Added and refreshed root/current-state documentation through PRs #299, #300 and #308.
- Added `loto-sklearn`, a dynamic all-estimator scikit-learn discovery/smoke/certification surface in PR #301 without changing Broad v1=174.
- Added process-parallel six-game Broad campaign execution, CPU affinity/thread controls, live `progress.json` status and aggregate artifacts in PR #302.
- Completed the Broad isotonic calibrated logistic factory/routing path in PR #303.
- Routed scheduler GPU leases into XGBoost and CatBoost constructors and verified bounded real GPU activity on exact source in PR #304.
- Added a fail-closed LightGBM accelerator probe in PR #305; the resolved LightGBM 4.7.0 build does not support the CUDA tree learner but its OpenCL `device_type="gpu"` backend was verified.
- Routed LightGBM candidate/position workers through the verified OpenCL GPU contract in PR #306 without claiming CUDA support.
- Normalized the sktime P1 formal input contract and restored the fixed four-model formal P1 verification path in PR #307.
- Refreshed repository current-state documentation and added the skforecast 0.23.0 operator-local runtime evidence document in PR #310 while keeping source-local evidence distinct from current-main certification.
- Aligned `docs/LIBRARY_MODEL_COMPATIBILITY_MATRIX.md` with the post-#310 sktime/skforecast/tree-GPU evidence boundary in PR #312.
- Reconciled Darts evidence and corrected the campaign denominator boundary in PR #311: current `loto3 campaign --plan-only` plans Broad **174 × 6 = 1,044** rows; combined Broad+Probabilistic **250 × 6 = 1,500** remains an accounting denominator rather than a current single-command planner output.
- Stabilized README audit metadata after PR #311 in PR #313.
- Added a consolidated current change summary and refreshed status/verification/handoff/execution documentation from current `main@0fb8d2e954b8ab08a8663c42792a6b3b67dc1e9d`.
- Recorded Draft PR #309 GluonTS P6/P7 evidence as `EXACT_HEAD_VERIFIED / MAIN_PENDING`: exact head `edba730a4f2c944c1ccc0bee510f7ce34833b6c3` verified latest 9/9 + compat 9/9 CPU lifecycles and P7D `VALID/VERIFIED`, without representing that result as merged current-main certification.

### Added

- Added atomic `BUILD_INFO.json` generation with package version, schema version, Git commit/dirty state and timestamps.
- Added version-consistency, dashboard, CLI, package-metadata, BUILD_INFO and README tests.
- Added the merged `uv run loto3 campaign` Broad all-model × six-game development evaluation surface with fail-visible coverage rows, Hit@±1-first metrics, mandatory baselines, seed summaries and prediction sealing.
- Added explicit MAP/WITHIN_TAU constrained select-game decoding.
- Added `docs/CURRENT_HANDOFF.md`, `docs/CURRENT_VERIFICATION_REPORT.md`, `docs/CURRENT_RUNBOOK.md`, `docs/CURRENT_MODEL_EXECUTION_ADDENDUM.md` and `docs/CAPABILITIES_AND_OPERATIONS.md` as current-state entry points while retaining older reports as historical evidence.
- Added GitHub repository observability/operations documentation and Actions summary workflows in PR #273.
- Added an evidence-aware static visual dashboard and explicit GitHub Pages deployment gate in PR #274; public Pages activation remains separately gated.
- Added the GitHub operations control-center/documentation classification layer in PR #276.
- Added Expanded Inventory v2 foundation in PR #293 while preserving Broad v1 and combined accounting denominators; AutoGluon expands from one umbrella to 29 source model identities + 8 unique ensemble identities.
- Added Toto 2.0 family manifest / 22M provenance foundation in PR #295 and 22M runtime-certification infrastructure in PR #296. Formal 22M runtime certification remains separately blocked by the native-Linux external GPU process/release gate (#297).
- Added `docs/SKLEARN_ALL_MODELS.md`, `docs/PARALLEL_UNIFIED_CAMPAIGN.md` and `docs/LIGHTGBM_GPU_CERTIFICATION.md` for newer execution/runtime surfaces.
- Added `docs/SKFORECAST_RUNTIME_CERTIFICATION.md` in PR #310 to record bounded skforecast 0.23.0 operator-local evidence, including core forecasters, RNN GPU/CPU fallback, Chronos-2, TimesFM 2.5, Moirai-2 compatibility-override behavior, TabICL artifact verification and the TabPFN-TS authentication block.
- Added `docs/CURRENT_CHANGE_SUMMARY.md` as the concise implementation/history entry point for the current repository state.

### Current evidence boundaries

- Broad v1 remains **174** and is not rewritten by dynamic or Expanded v2 inventories.
- Probabilistic effective v1 is **76** under current loader behavior.
- Combined Broad+Probabilistic accounting is **250** identities / **1,500** six-game cells.
- Current single `loto3 campaign --plan-only` is Broad-only: **174 × 6 = 1,044** rows.
- Expanded v2 Phase 1 derives **210** implementation identities; later phases remain open.
- `REGISTERED`, `ROUTABLE`, `RUNTIME_CERTIFIED`, `OOF_EVALUATED`, `HOLDOUT_EVALUATED`, `PROSPECTIVE_EVALUATED` and `PROMOTION_ELIGIBLE` remain separate states.
- sktime registry discovery/importability is broader than the formally verified four-model P1 runtime matrix.
- skforecast operator-local runtime evidence is **not** equivalent to current-main Expanded v2 repository integration.
- Darts local Torch/NLinear/DLinear GPU evidence is **not** a source-complete or all-export current-main certification; #286 / TAJ-27 remains active.
- GluonTS PR #309 exact-head runtime evidence is **not** merged current-main certification while the PR remains open/draft.
- Moirai-2 skforecast-adapter evidence passed only under a controlled unsupported dependency metadata override; normal dependency routability remains blocked.
- TabICL v2 operator runtime and checkpoint SHA-256 were verified for the recorded exact source/artifact.
- TabPFN-TS V3 inference is not certified; the operator diagnosis found invalid/expired authentication before checkpoint download/inference.
- Toto 22M formal runtime certification remains blocked pending #297 external GPU PID/VRAM/release evidence.
- Holdout remains **CLOSED**.
- Prospective remains **CLOSED**.
- Automatic promotion/retraining/registry write remains **FORBIDDEN**.
