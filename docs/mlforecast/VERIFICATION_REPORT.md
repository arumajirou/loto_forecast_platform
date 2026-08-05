# MLForecast verification report

## Report status

`LOCAL_CONTRACT_HARDENED / PORTABLE_BUNDLE_VERIFIER_VERIFIED / SOURCE_HANDOFF_VERIFIED / INSTALLED_RUNTIME_PENDING / GITHUB_ACTIONS_RUNNER_BLOCKED`

## Frozen upstream

- package: `mlforecast==1.1.0`
- tag: `v1.1.0`
- upstream commit: `a1609efddf8cf1a83510a50cd5487b66f32271c6`
- wheel: `mlforecast-1.1.0-py3-none-any.whl`
- wheel SHA-256: `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748`

## Completed verification

| Gate | Result |
|---|---|
| Full focused MLForecast tests after source handoff integration | 55 passed |
| Installed-runtime smoke | 1 skipped |
| Bundle/verifier tests | 13 passed |
| Python compileall | PASS |
| AST parse | 22 files PASS |
| Line-length inspection | 0 violations |
| Shell syntax | PASS |
| Deterministic ZIP equality | PASS |
| ZIP-slip and unsafe-member rejection | PASS |
| Source-root and nested-symlink rejection | PASS |
| Sidecar mismatch and archive-limit rejection | PASS |
| External verification-report generation | PASS |
| Source handoff tests | 7 passed |
| Source handoff build from temporary Git repository | HANDOFF_BUILT |
| Independent source handoff verification | HANDOFF_VERIFIED |
| Ruff | NOT RUN; tool unavailable and registry DNS blocked |

The skip and unavailable Ruff execution are not counted as success.

## GitHub Actions boundary

Recent Actions jobs completed with zero executed steps and no downloadable log. Checkout, Ruff, compileall, pytest, and runtime certification did not begin. These runs are classified as `GITHUB_ACTIONS_RUNNER_BLOCKED`, not as code success or code failure.

## Installed runtime boundary

The current isolated environment cannot resolve the official PyPI file host. The exact wheel bytes could not be downloaded and installed here. Therefore the following remain pending:

- exact wheel-file execution for the current PR head;
- Core Ridge real fit/predict/save/load certification;
- AutoRidge two-trial fit/predict/save/load certification;
- emitted `RUNTIME_CERTIFIED` evidence bundle.

Historical installation or import logs from another head do not certify the current implementation.

## Accuracy boundary

No claim is made for real-data accuracy improvement, baseline superiority, Holdout success, Prospective success, or Hit@±1 target attainment. These require the later formal campaign using time-ordered partitions, multiple seeds, identical folds, and sealed Prospective predictions.

## Current next gate

Run `docs/mlforecast/run_runtime_certification.sh` on the target Linux environment, then independently verify the generated ZIP and sidecar. Only after `RUNTIME_CERTIFIED` and `BUNDLE_VERIFIED` should the formal multi-seed campaign begin.
