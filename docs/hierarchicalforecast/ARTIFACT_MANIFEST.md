# HierarchicalForecast artifact manifest

## Manifest status

- Component: HierarchicalForecast reconciliation runtime certification
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / PORTABLE_PUBLICATION_TESTS_PASS / CI_BLOCKED_RUNNER_START`

This document inventories source and generated artifacts. Machine-generated manifests and checksum
files remain the integrity roots for runtime evidence.

## Source implementation

| Path | Role |
|---|---|
| `src/loto/reconciliation/hierarchy.py` | upstream adapter, execution, and validation |
| `src/loto/reconciliation/runtime_certification.py` | deterministic 40-case runtime certification |
| `src/loto/reconciliation/package_certification.py` | runtime evidence and deterministic ZIP verification |
| `src/loto/reconciliation/portable_package_certification.py` | no-clobber hard-link or exclusive-copy publication |
| `scripts/hierarchicalforecast_target/constants.py` | formal constants and expected partition |
| `scripts/hierarchicalforecast_target/integrity.py` | filesystem, JSON, array, and SHA helpers |
| `scripts/hierarchicalforecast_target/runtime_verification.py` | independent runtime and 40-row verification |
| `scripts/hierarchicalforecast_target/package_verification.py` | source, ZIP, sidecar, and manifest verification |
| `scripts/hierarchicalforecast_target/operator.py` | target-machine orchestration |
| `scripts/hierarchicalforecast_target/quality_gate.py` | Ruff, mypy, focused, full-suite, and JUnit gate |
| `scripts/run_hierarchicalforecast_target_certification.py` | target runtime wrapper |
| `scripts/run_hierarchicalforecast_quality_gate.py` | local quality wrapper |
| `pyproject.toml` | dependencies, tool configuration, and portable console target |

The public console target is:

```text
loto-hierarchicalforecast-certify =
  loto.reconciliation.portable_package_certification:main
```

## Test artifacts

| Path | Current isolated evidence |
|---|---:|
| `tests/test_reconciliation.py` | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | 9 passed |
| `tests/test_reconciliation_console_script.py` | 2 passed |
| `tests/test_reconciliation_package_certification.py` | 11 passed |
| `tests/test_reconciliation_target_machine_certification.py` | 9 passed |
| `tests/test_reconciliation_target_operator.py` | 6 passed |
| `tests/test_reconciliation_quality_gate.py` | 9 passed |
| **Cumulative focused evidence** | **77 passed** |

The package and console subset was re-executed against exact published blobs:

```text
13 passed
compileall PASS
Python lines over 100 characters: 0
```

The total of 77 is from separate isolated runs. A formal combined invocation remains pending.

## Documentation

All paths below are under `docs/hierarchicalforecast/`:

- `README.md`
- `REQUIREMENTS.md`
- `SPECIFICATION.md`
- `ARCHITECTURE.md`
- `DATA_CONTRACT.md`
- `TEST_PLAN.md`
- `RUNTIME_CERTIFICATION.md`
- `TARGET_MACHINE_CERTIFICATION.md`
- `PORTABLE_PACKAGE_PUBLICATION.md`
- `QUALITY_GATE.md`
- `RUNBOOK.md`
- `VERIFICATION_REPORT.md`
- `HANDOFF.md`
- `CHANGELOG.md`
- `CI_BLOCKER.md`
- `ARTIFACT_MANIFEST.md`

## Integrity roots

| Evidence class | Integrity root |
|---|---|
| checked-in source and documentation | exact Git commit |
| runtime directory | runtime `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| transfer ZIP | `<runtime-run-id>.zip.sha256` |
| target operator execution | operator `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| local quality execution | quality `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |

Runtime, operator, and quality Run IDs are independent and must not be substituted for one another.

## Runtime evidence

```text
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
├── RUNTIME_CERTIFICATION.json
├── METHOD_RESULTS.json
├── INPUT_EVIDENCE.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS

artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
```

The ZIP additionally contains canonical `PACKAGE_MANIFEST.json`.

The package result records one publication method:

```text
hardlink
exclusive_copy
reused_existing
```

All methods preserve the no-overwrite contract. `exclusive_copy` uses `O_CREAT | O_EXCL`, flush,
`fsync`, final SHA-256 verification, and partial-file cleanup.

## Target-operator evidence

```text
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
├── command stdout/stderr logs
├── COMMANDS.json
├── OPERATOR_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

## Local-quality evidence

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
├── sync, dependency, Ruff, compileall, mypy, and pytest logs
├── focused.junit.xml
├── full.junit.xml
├── COMMANDS.json
├── QUALITY_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Focused JUnit must record exactly 77 tests with zero failures and errors. Full-suite JUnit must
record zero failures and errors.

## Verification commands

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <runtime-run-id>.zip.sha256
unzip -t <runtime-run-id>.zip
cd <runtime-run-id>
sha256sum -c SHA256SUMS

cd artifacts/hierarchicalforecast-target-runs/<operator-run-id>
sha256sum -c SHA256SUMS

cd artifacts/hierarchicalforecast-quality-runs/<quality-run-id>
sha256sum -c SHA256SUMS
```

## Pending formal artifacts

- real installed `hierarchicalforecast==1.5.1` 40-case runtime bundle;
- real target-operator evidence for the current reviewed head;
- real mounted-drive publication evidence including `publication_method`;
- formal quality evidence with Ruff, mypy, exact 77 focused tests, and full pytest;
- GitHub Actions logs and results containing real workflow steps.

Issue #61 tracks the GitHub Actions runner-start blocker.

## Handoff rule

Record and transfer the exact Git commit, runtime/operator/quality Run IDs, installed version,
40-case totals, focused/full JUnit totals, publication method, ZIP SHA-256, all three `SHA256SUMS`
files, and GitHub Actions run/job IDs.

Do not overwrite a runtime directory, operator directory, quality directory, mismatched ZIP, or
mismatched sidecar. Preserve inconsistencies as incident evidence and create a new Run ID.
