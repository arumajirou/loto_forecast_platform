# HierarchicalForecast artifact manifest

## Manifest status

- Component: HierarchicalForecast reconciliation runtime certification
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / PROMOTION_GATE_TESTS_PASS / CI_BLOCKED_RUNNER_START`

Machine-generated manifests and checksum files remain the integrity roots for runtime evidence.

## Source implementation

| Path | Role |
|---|---|
| `src/loto/reconciliation/hierarchy.py` | upstream adapter, execution, and validation |
| `src/loto/reconciliation/runtime_certification.py` | deterministic 40-case runtime certification |
| `src/loto/reconciliation/package_certification.py` | runtime evidence and deterministic ZIP verification |
| `src/loto/reconciliation/portable_package_certification.py` | no-clobber hard-link or exclusive-copy publication |
| `src/loto/reconciliation/package_verifier.py` | read-only transferred ZIP and sidecar verification |
| `scripts/hierarchicalforecast_target/constants.py` | formal constants and expected partition |
| `scripts/hierarchicalforecast_target/integrity.py` | filesystem, JSON, array, and SHA helpers |
| `scripts/hierarchicalforecast_target/runtime_verification.py` | independent runtime and 40-row verification |
| `scripts/hierarchicalforecast_target/package_verification.py` | source, ZIP, sidecar, and manifest verification |
| `scripts/hierarchicalforecast_target/operator.py` | target-machine orchestration |
| `scripts/hierarchicalforecast_target/quality_gate.py` | Ruff, mypy, focused, full-suite, and JUnit gate |
| `scripts/hierarchicalforecast_target/promotion_gate.py` | chained local gates and cross-root integrity |
| `scripts/run_hierarchicalforecast_target_certification.py` | target runtime wrapper |
| `scripts/run_hierarchicalforecast_quality_gate.py` | local quality wrapper |
| `scripts/run_hierarchicalforecast_promotion_gate.py` | complete local promotion wrapper |
| `pyproject.toml` | dependencies, tool configuration, and console targets |

Public console targets:

```text
loto-hierarchicalforecast-certify =
  loto.reconciliation.portable_package_certification:main

loto-hierarchicalforecast-verify-package =
  loto.reconciliation.package_verifier:main
```

## Test artifacts

| Path | Current isolated evidence |
|---|---:|
| `tests/test_reconciliation.py` | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | 9 passed |
| `tests/test_reconciliation_console_script.py` | 2 passed |
| `tests/test_reconciliation_package_certification.py` | 11 passed |
| `tests/test_reconciliation_package_verifier.py` | 7 passed |
| `tests/test_reconciliation_target_machine_certification.py` | 9 passed |
| `tests/test_reconciliation_target_operator.py` | 6 passed |
| `tests/test_reconciliation_promotion_gate.py` | 8 passed |
| `tests/test_reconciliation_quality_gate.py` | 9 passed |
| **Cumulative focused evidence** | **92 passed** |

Promotion-gate files were executed against exact published Git blobs:

```text
promotion tests 8 passed
compileall PASS
Python lines over 100 characters: 0
wrapper --help PASS
```

The total of 92 is from separate isolated runs. A formal combined invocation remains pending.

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
- `PACKAGE_VERIFIER.md`
- `QUALITY_GATE.md`
- `PROMOTION_GATE.md`
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
| transfer ZIP | `<runtime-run-id>.zip.sha256` plus internal manifests |
| target operator execution | operator `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| local quality execution | quality `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| local promotion execution | promotion `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |

Runtime, operator, quality, and promotion Run IDs are independent. The promotion report links and
cross-checks the other roots but does not replace them. The standalone verifier validates the
transferred ZIP and sidecar without creating another evidence root.

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

The ZIP additionally contains canonical `PACKAGE_MANIFEST.json`. The package result records
`hardlink`, `exclusive_copy`, or `reused_existing` as its publication method.

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

Focused JUnit must record exactly 92 tests with zero failures and errors. Full-suite JUnit must
record zero failures and errors.

## Local-promotion evidence

```text
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
├── quality stdout/stderr logs
├── target stdout/stderr logs
├── package-verification stdout/stderr logs
├── COMMANDS.json
├── PROMOTION_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Successful local promotion records `LOCAL_GATES_VERIFIED`, `formal_success=true`,
`ready_for_review=false`, and `ci_required=true`.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

## Verification commands

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <runtime-run-id>.zip.sha256

uv run --locked loto-hierarchicalforecast-verify-package \
  --zip <runtime-run-id>.zip

cd <runtime-run-id>
sha256sum -c SHA256SUMS

cd artifacts/hierarchicalforecast-target-runs/<operator-run-id>
sha256sum -c SHA256SUMS

cd artifacts/hierarchicalforecast-quality-runs/<quality-run-id>
sha256sum -c SHA256SUMS

cd artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>
sha256sum -c SHA256SUMS
```

## Pending formal artifacts

- formal promotion evidence for the current reviewed head;
- real installed `hierarchicalforecast==1.5.1` 40-case runtime bundle;
- real mounted-drive publication evidence including `publication_method`;
- standalone verification report for the real transferred ZIP;
- formal quality evidence with Ruff, mypy, exact 92 focused tests, and full pytest;
- GitHub Actions logs and results containing real workflow steps.

Issue #61 tracks the GitHub Actions runner-start blocker.

## Handoff rule

Record and transfer the exact Git commit, runtime/operator/quality/promotion Run IDs, installed
version, 40-case totals, focused/full JUnit totals, publication method, standalone-verifier JSON
result, ZIP SHA-256, all four `SHA256SUMS` files, and GitHub Actions run/job IDs.

Do not overwrite any evidence directory, mismatched ZIP, or mismatched sidecar. Preserve
inconsistencies as incident evidence and create a new Run ID.
