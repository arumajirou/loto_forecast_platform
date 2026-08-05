# HierarchicalForecast branch changelog

## Unreleased — PR #48

### Added

- actual HierarchicalForecast `fit_predict()` execution through the project reconciliation adapter
- support for all ten registered upstream reconciler class names
- grouped-hierarchy compatibility checks and explicit strict-tree rejection
- paired in-sample actual and fitted input support for methods that require it
- output shape, finite-value, and coherence validation
- deterministic 40-case runtime-certification harness for four select-family games
- exact-version and module/distribution consistency checks
- runtime evidence including configuration, data, source, code, and output SHA-256 values
- atomic runtime artifact writes and portable `SHA256SUMS`
- immutable deterministic evidence ZIP and ZIP SHA-256 sidecar
- canonical package manifest and ZIP member metadata checks
- pre-publication ZIP verification
- structured configuration, certification-harness, and packaging failure statuses
- operational console entry point: `loto-hierarchicalforecast-certify`
- runtime certification documentation, RUNBOOK, verification report, and handoff
- focused tests for adapter execution, all-method coverage, runtime certification, console entry,
  immutable packaging, corruption rejection, path traversal, and failure continuation

### Changed

- the adapter no longer returns constructor-only `AVAILABLE` as proof of runtime success
- successful runtime status is now `VERIFIED` only after actual execution and validation
- the formal console command now executes runtime certification and evidence packaging together
- existing identical ZIPs are reused rather than overwritten
- mismatched existing ZIPs and sidecars are retained and rejected as incident evidence
- packaging now verifies temporary ZIPs before publication
- error output now distinguishes configuration, certification, and package phases

### Fixed

- sparse reconciler inputs are converted to CSR before upstream execution
- constructor and `fit_predict()` arguments are filtered against the installed signatures
- unsupported grouped hierarchies fail before strict-tree reconciler construction
- missing paired in-sample evidence fails before execution
- non-finite, wrong-shape, or incoherent upstream results cannot be promoted to success
- one method exception no longer terminates the remaining formal matrix
- invalid ZIPs are no longer published before verification
- existing package and sidecar evidence is no longer silently replaced
- path traversal, duplicate ZIP members, unsafe checksum paths, and manifest coverage mismatches are
  rejected

### Verification

Focused evidence across separate isolated runs:

- existing reconciliation tests: 19 passed
- all-method state matrix: 12 passed
- runtime-certification tests: 9 passed
- console-entry tests: 2 passed
- immutable package-certification tests: 11 passed
- total unique focused evidence: 53 passed

Additional checks:

- compileall: PASS
- Python maximum line length 100: PASS
- simple secret-pattern scan: PASS
- remote/local Git blob equality: PASS
- unresolved PR review threads: 0

### Known limitations

- real installed `hierarchicalforecast==1.5.1` 40-case execution remains pending
- installed console-script smoke remains blocked in the isolated build environment
- repository-wide Ruff, mypy, and pytest are not locally certified
- GitHub Actions remains blocked before workflow step creation
- no forecasting accuracy, Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective claim is made

### Safety

- raw runtime artifacts are written under a new Run ID and are not overwritten
- mismatched ZIP and sidecar evidence is preserved
- no direct push to `main`
- no force push
- no auto-merge
- Draft PR retained
