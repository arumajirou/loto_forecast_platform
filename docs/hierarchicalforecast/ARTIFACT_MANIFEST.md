# HierarchicalForecast artifact manifest

## Manifest status

- Component: HierarchicalForecast reconciliation runtime certification and hardened target operator
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State:
  `PARTIALLY_VERIFIED / HARDENED_OPERATOR_TESTS_PASS / CI_BLOCKED_RUNNER_START / NOT_READY`
- Source integrity root: exact Git commit used by the target operator
- Runtime integrity root: per-run `ARTIFACT_MANIFEST.json` and `SHA256SUMS`
- Transfer integrity root: `<runtime-run-id>.zip.sha256`
- Operator integrity root: per-operator-run `ARTIFACT_MANIFEST.json` and `SHA256SUMS`

This document inventories the artifacts and their roles. It does not replace machine-generated
manifests or checksum files.

## Core source artifacts

| Path | Role | Verification state |
|---|---|---|
| `src/loto/reconciliation/hierarchy.py` | upstream adapter, execution, shape/finite/coherence validation | focused contract verified |
| `src/loto/reconciliation/runtime_certification.py` | deterministic forty-case orchestration and runtime evidence | verified with test doubles; real 1.5.1 pending |
| `src/loto/reconciliation/package_certification.py` | runtime verification and immutable deterministic package | focused package verification passed |
| `pyproject.toml` | registers `loto-hierarchicalforecast-certify` | entry-point resolution verified |

## Hardened target source artifacts

| Path | Role | Verification state |
|---|---|---|
| `scripts/run_hierarchicalforecast_target_certification.py` | standard-library bootstrap wrapper | blob equality, compile, and help verified |
| `scripts/hierarchicalforecast_target/constants.py` | frozen formal version, geometry, and artifact names | blob equality verified |
| `scripts/hierarchicalforecast_target/integrity.py` | safe paths, symlink rejection, JSON, checksums, array evidence | focused verification passed |
| `scripts/hierarchicalforecast_target/runtime_verification.py` | exact runtime files, forty rows, shapes, finite/coherence, inputs | focused verification passed |
| `scripts/hierarchicalforecast_target/package_verification.py` | source hashes, ZIP metadata, sidecar, manifests, package evidence | focused verification passed |
| `scripts/hierarchicalforecast_target/operator.py` | locked commands, pre/postflight Git, operator evidence, exit states | focused operator tests passed |

The target implementation is split into reviewable responsibilities. Production execution requires
`--expected-git-sha` and does not expose synchronization bypass.

## Test artifacts

| Path | Scope | Current isolated evidence |
|---|---|---:|
| `tests/test_reconciliation.py` | adapter execution and validation | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | ten methods and expected state partition | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | formal matrix, artifacts, failure behavior | 9 passed |
| `tests/test_reconciliation_console_script.py` | entry-point metadata and callable | 2 passed |
| `tests/test_reconciliation_package_certification.py` | immutable ZIP, sidecar, corruption/path rejection | 11 passed |
| `tests/test_reconciliation_target_machine_certification.py` | hardened runtime/package/source verification | 9 passed |
| `tests/test_reconciliation_target_operator.py` | locked operator controls and Git drift | 6 passed |
| `tests/hierarchicalforecast_target_fixtures.py` | synthetic sealed evidence support | support fixture |

Unique focused evidence across separate isolated runs: 68 passed.

The hardened target subset was executed together against an exact local reconstruction of its
published Git blobs: 15 passed.

## Documentation artifacts

| Path | Purpose |
|---|---|
| `docs/hierarchicalforecast/README.md` | component entry point and status |
| `docs/hierarchicalforecast/REQUIREMENTS.md` | acceptance requirements and promotion gates |
| `docs/hierarchicalforecast/SPECIFICATION.md` | adapter, matrix, runtime, status, and package specification |
| `docs/hierarchicalforecast/ARCHITECTURE.md` | layers, data flow, trust boundaries, failure isolation |
| `docs/hierarchicalforecast/DATA_CONTRACT.md` | input/output, shape, finite, coherence, determinism contracts |
| `docs/hierarchicalforecast/TEST_PLAN.md` | focused, hardened target, real runtime, full-suite, and CI plan |
| `docs/hierarchicalforecast/RUNTIME_CERTIFICATION.md` | runtime certifier reference |
| `docs/hierarchicalforecast/TARGET_MACHINE_CERTIFICATION.md` | locked operator, independent checks, evidence, acceptance |
| `docs/hierarchicalforecast/RUNBOOK.md` | operational execution and diagnosis |
| `docs/hierarchicalforecast/VERIFICATION_REPORT.md` | current evidence, findings, gaps, and readiness verdict |
| `docs/hierarchicalforecast/HANDOFF.md` | next-operator commands and prohibited shortcuts |
| `docs/hierarchicalforecast/CHANGELOG.md` | branch-level change record |
| `docs/hierarchicalforecast/CI_BLOCKER.md` | zero-step GitHub Actions diagnosis |
| `docs/hierarchicalforecast/ARTIFACT_MANIFEST.md` | this source/runtime/operator inventory |

## Runtime artifact bundle

Every certifier invocation creates a unique directory:

```text
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
```

Required contents:

| File | Purpose | Integrity binding |
|---|---|---|
| `RUNTIME_CERTIFICATION.json` | overall configuration, dependency, environment, and summary | manifest + SHA256SUMS |
| `METHOD_RESULTS.json` | all forty game/method records | manifest + SHA256SUMS |
| `INPUT_EVIDENCE.json` | deterministic input shape/hash evidence | manifest + SHA256SUMS |
| `ARTIFACT_MANIFEST.json` | primary artifact byte counts and hashes | SHA256SUMS |
| `SHA256SUMS` | portable checksum coverage for primary JSON files | packaged and reverified |

The target operator requires exact directory coverage, regular files, no symlinks, exact checksum
coverage, and a unique three-row runtime manifest.

## Runtime transfer package

Sibling outputs:

```text
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
```

ZIP contents:

```text
<runtime-run-id>/RUNTIME_CERTIFICATION.json
<runtime-run-id>/METHOD_RESULTS.json
<runtime-run-id>/INPUT_EVIDENCE.json
<runtime-run-id>/ARTIFACT_MANIFEST.json
<runtime-run-id>/SHA256SUMS
<runtime-run-id>/PACKAGE_MANIFEST.json
```

The ZIP sidecar binds final archive bytes. The package manifest binds member paths, sizes, hashes,
certification status, Run ID, and content-set hash. The target operator independently verifies ZIP
metadata, canonical manifest bytes, CRC, member coverage, sizes, and hashes.

## Operator evidence bundle

Every target attempt creates a separate directory:

```text
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
```

Possible contents:

```text
sync.stdout.log
sync.stderr.log
version.stdout.log
version.stderr.log
certification.stdout.log
certification.stderr.log
COMMANDS.json
OPERATOR_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

Failure attempts retain available logs and structured status. The operator manifest and checksums do
not replace the runtime manifest, runtime checksums, or ZIP sidecar.

## Integrity relationships

```text
Git commit
  ├── hierarchy.py SHA-256
  ├── runtime_certification.py SHA-256
  └── target operator source

runtime Run ID
  ├── runtime ARTIFACT_MANIFEST.json
  ├── runtime SHA256SUMS
  └── ZIP + ZIP sidecar

operator Run ID
  ├── command logs
  ├── OPERATOR_REPORT.json
  ├── operator ARTIFACT_MANIFEST.json
  └── operator SHA256SUMS
```

Formal success requires all three integrity roots to agree on the exact execution context.

## Verification commands

The operator performs independent checks automatically. Portable receiver checks remain:

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <runtime-run-id>.zip.sha256
unzip -t <runtime-run-id>.zip
cd <runtime-run-id>
sha256sum -c SHA256SUMS

cd ../../hierarchicalforecast-target-runs/<operator-run-id>
sha256sum -c SHA256SUMS
```

## Evidence pending

The manifest records the following as pending:

- real installed `hierarchicalforecast==1.5.1` forty-case runtime and operator bundles;
- Ruff result;
- mypy result for the supported typed scope;
- combined focused-test invocation;
- repository-wide pytest result;
- GitHub Actions with real steps, logs, and passing checks.

Issue #61 tracks the GitHub Actions runner-start blocker.

## Handoff rule

Transfer the runtime ZIP and sidecar together, plus the operator evidence directory or a separately
sealed archive of it. Record:

- exact Git commit;
- operator Run ID;
- runtime Run ID;
- exact installed version;
- status and case counts;
- 24 executed and 16 rejected rows;
- runtime and operator SHA verification results;
- ZIP SHA-256;
- GitHub Actions run and job identifiers.

Do not overwrite source runtime evidence, operator evidence, a mismatched ZIP, or a mismatched
sidecar. Investigate the mismatch and create new Run IDs.
