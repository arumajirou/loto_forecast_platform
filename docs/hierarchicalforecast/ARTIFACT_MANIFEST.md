# HierarchicalForecast artifact manifest

## Manifest status

- Component: HierarchicalForecast reconciliation runtime certification
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / CI_BLOCKED_RUNNER_START / NOT_READY_FOR_REVIEW`
- Integrity root for source artifacts: exact Git commit at execution or handoff time
- Integrity root for runtime artifacts: per-run `ARTIFACT_MANIFEST.json` and `SHA256SUMS`
- Integrity root for transfer package: `<run-id>.zip.sha256`

This document inventories the component artifacts and their roles. It does not replace the
machine-generated runtime manifest or SHA-256 files.

## Source implementation artifacts

| Path | Role | Verification state |
|---|---|---|
| `src/loto/reconciliation/hierarchy.py` | upstream adapter, dispatch, execution, shape/finite/coherence validation | focused contract verified |
| `src/loto/reconciliation/runtime_certification.py` | formal 40-case orchestration and runtime evidence writer | verified with deterministic test doubles; real 1.5.1 pending |
| `src/loto/reconciliation/package_certification.py` | evidence verification, immutable deterministic ZIP, sidecar, CLI | focused package verification passed |
| `pyproject.toml` | registers `loto-hierarchicalforecast-certify` | entry-point resolution verified |

## Test artifacts

| Path | Scope | Current isolated evidence |
|---|---|---:|
| `tests/test_reconciliation.py` | adapter execution and validation contract | 19 passed |
| `tests/test_reconciliation_upstream_matrix.py` | all ten classes and expected state partition | 12 passed |
| `tests/test_reconciliation_runtime_certification.py` | formal matrix, artifacts, dependency/version/runtime failure behavior | 9 passed |
| `tests/test_reconciliation_console_script.py` | console entry metadata and callable resolution | 2 passed |
| `tests/test_reconciliation_package_certification.py` | immutable ZIP, sidecar, corruption/path rejection, phase failures | 11 passed |

Unique focused evidence across separate isolated runs: 53 passed.

## Documentation artifacts

| Path | Purpose |
|---|---|
| `docs/hierarchicalforecast/REQUIREMENTS.md` | acceptance requirements and promotion gates |
| `docs/hierarchicalforecast/SPECIFICATION.md` | public command, matrix, artifacts, statuses, and package specification |
| `docs/hierarchicalforecast/ARCHITECTURE.md` | layer boundaries, data flow, trust boundaries, and failure isolation |
| `docs/hierarchicalforecast/DATA_CONTRACT.md` | input/output shapes, invariants, determinism, artifact and immutability contracts |
| `docs/hierarchicalforecast/TEST_PLAN.md` | focused, target-machine, full-suite, and CI verification plan |
| `docs/hierarchicalforecast/RUNTIME_CERTIFICATION.md` | operator-facing runtime certification reference |
| `docs/hierarchicalforecast/RUNBOOK.md` | formal execution, verification, diagnosis, and handoff procedure |
| `docs/hierarchicalforecast/VERIFICATION_REPORT.md` | current evidence, gaps, and formal readiness verdict |
| `docs/hierarchicalforecast/HANDOFF.md` | next-operator commands, evidence requirements, and prohibited shortcuts |
| `docs/hierarchicalforecast/CHANGELOG.md` | branch-level added, changed, fixed, and known-limitation record |
| `docs/hierarchicalforecast/CI_BLOCKER.md` | zero-step GitHub Actions diagnosis and owner checklist |
| `docs/hierarchicalforecast/ARTIFACT_MANIFEST.md` | this component artifact inventory |

## Runtime artifact bundle

Every invocation creates a unique run directory:

```text
artifacts/hierarchicalforecast-runtime/<run-id>/
```

Required contents:

| File | Purpose | Integrity binding |
|---|---|---|
| `RUNTIME_CERTIFICATION.json` | overall status, configuration, dependency, environment, and summary evidence | `ARTIFACT_MANIFEST.json` + `SHA256SUMS` |
| `METHOD_RESULTS.json` | all formal method/game case records | `ARTIFACT_MANIFEST.json` + `SHA256SUMS` |
| `INPUT_EVIDENCE.json` | deterministic input shape/hash evidence | `ARTIFACT_MANIFEST.json` + `SHA256SUMS` |
| `ARTIFACT_MANIFEST.json` | primary artifact byte counts and SHA-256 values | included in `SHA256SUMS` |
| `SHA256SUMS` | portable checksums for all primary JSON artifacts | packaged and reverified |

## Transfer package

Sibling outputs:

```text
artifacts/hierarchicalforecast-runtime/<run-id>.zip
artifacts/hierarchicalforecast-runtime/<run-id>.zip.sha256
```

ZIP contents:

```text
<run-id>/RUNTIME_CERTIFICATION.json
<run-id>/METHOD_RESULTS.json
<run-id>/INPUT_EVIDENCE.json
<run-id>/ARTIFACT_MANIFEST.json
<run-id>/SHA256SUMS
<run-id>/PACKAGE_MANIFEST.json
```

`PACKAGE_MANIFEST.json` binds the runtime files by path, byte count, and SHA-256 and records the
Run ID, certification status, and content-set SHA-256. The sidecar binds the final ZIP bytes.

## Verification commands

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <run-id>.zip.sha256
unzip -t <run-id>.zip
cd <run-id>
sha256sum -c SHA256SUMS
```

## Evidence not yet available

The manifest records the following as pending rather than silently treating them as successful:

- real installed `hierarchicalforecast==1.5.1` 40-case runtime bundle
- installed console-script execution in the isolated review environment
- Ruff result
- mypy result for the supported typed scope
- repository-wide pytest result
- GitHub Actions execution with real steps and logs

Issue #61 tracks the GitHub Actions runner-start blocker.

## Handoff rule

Transfer the ZIP and sidecar together. Record the following in the verification report or handoff:

- Run ID
- Git commit
- exact installed HierarchicalForecast version
- certification status and case counts
- ZIP SHA-256
- verification command results
- GitHub Actions run and job IDs

Do not overwrite source runtime evidence, a mismatched ZIP, or a mismatched sidecar. Create a new
Run ID after investigating any inconsistency.
