# MLForecast verification report

## Report status

`LOCAL_CONTRACT_HARDENED / PORTABLE_BUNDLE_VERIFIER_VERIFIED / STRICT_SOURCE_HANDOFF_GUARD_VERIFIED / INSTALLED_RUNTIME_PENDING / GITHUB_ACTIONS_RUNNER_BLOCKED`

## Frozen upstream

- package: `mlforecast==1.1.0`
- tag: `v1.1.0`
- upstream commit: `a1609efddf8cf1a83510a50cd5487b66f32271c6`
- wheel: `mlforecast-1.1.0-py3-none-any.whl`
- wheel SHA-256: `0043190f540510979c7709bb69267caa9ac325a11fa49298cf3425307200e748`

## Completed verification before strict guard addition

| Gate | Result |
|---|---|
| Full focused MLForecast tests after source handoff integration | 55 passed |
| Installed-runtime smoke | 1 skipped |
| Bundle/verifier tests | 13 passed |
| Source handoff tests | 7 passed |
| Python compileall | PASS |
| AST parse | 22 files PASS |
| Line-length inspection | 0 violations |
| Shell syntax | PASS |
| Deterministic ZIP equality | PASS |
| ZIP-slip and unsafe-member rejection | PASS |
| Source-root and nested-symlink rejection | PASS |
| Sidecar mismatch and archive-limit rejection | PASS |
| External verification-report generation | PASS |
| Source handoff build from temporary Git repository | HANDOFF_BUILT |
| Independent source handoff verification | HANDOFF_VERIFIED |
| Ruff | NOT RUN; tool unavailable and registry DNS blocked |

The installed-runtime skip and unavailable Ruff execution are not counted as success.

## Strict source handoff guard verification

The formal source handoff path now uses `loto.mlforecast.handoff_guard` for both construction and acceptance. It adds pre/post Git-state checks and an independent stricter archive verifier around the compatibility builder.

| Guard gate | Result |
|---|---|
| Focused strict-guard tests | 10 passed |
| Guard module Python compilation | PASS |
| Guard and guard-test line-length inspection | 0 violations |
| Updated handoff shell syntax | PASS |
| Local tested guard blob equals GitHub blob | PASS |
| Local tested guard-test blob equals GitHub blob | PASS |
| Local tested shell blob equals GitHub blob | PASS |
| Dirty `pyproject.toml` / `uv.lock` rejection | PASS |
| Detached-HEAD rejection | PASS |
| Repository-state change protection | PASS |
| ZIP and sidecar symlink rejection | PASS |
| Unexpected member rejection | PASS |
| File-count and uncompressed-size limits | PASS |
| CRC and non-portable path checks | PASS |
| Manifest, sums, provenance, VERSION, frozen-base and upstream cross-checks | PASS |

The exact combined `pytest -q tests/mlforecast` suite was not rerun after adding the strict guard. Therefore the previous 55-test result and the new 10-test guard result are reported separately and are not represented as 65 combined passes.

## Final scope verification

The current pull-request file list contains 42 files. Every file is under exactly one of these dedicated paths:

- `configs/mlforecast/**`
- `docs/mlforecast/**`
- `src/loto/mlforecast/**`
- `tests/mlforecast/**`

No final diff remains for `noop`, `pyproject.toml`, `uv.lock`, GitHub workflows, common CLI/catalog code, the root README, or PR #43 paths.

## Source handoff acceptance boundary

Formal construction and verification use:

```bash
bash docs/mlforecast/build_handoff_bundle.sh
```

or, for a received package:

```bash
uv run --frozen -- \
  python -m loto.mlforecast.handoff_guard \
  --verify \
  --zip /absolute/path/mlforecast-handoff-<SHA>.zip \
  --sha256 /absolute/path/mlforecast-handoff-<SHA>.zip.sha256
```

`HANDOFF_VERIFIED` means the archive is complete and internally consistent under the strict guard. It does not authenticate the publisher, prove that the supplied commit exists in a trusted remote, or replace installed runtime certification.

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

## Current next gates

1. Run the exact combined focused suite and Ruff on the target Linux environment.
2. Build and verify the source handoff ZIP using the strict guard.
3. Run `docs/mlforecast/run_runtime_certification.sh` with the official wheel.
4. Begin the formal multi-seed campaign only after both `RUNTIME_CERTIFIED` and `BUNDLE_VERIFIED` are present.
