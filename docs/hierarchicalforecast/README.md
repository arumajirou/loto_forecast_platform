# HierarchicalForecast reconciliation certification

## Status

`PARTIALLY_VERIFIED / CI_BLOCKED_RUNNER_START / NOT_READY_FOR_REVIEW`

PR #48 replaces constructor-only HierarchicalForecast availability reporting with actual upstream
execution, fail-closed validation, deterministic runtime certification, and an immutable
SHA-256-sealed evidence package.

The PR remains Draft until both of these external gates pass:

1. real installed `hierarchicalforecast==1.5.1` execution for all 40 formal cases
2. GitHub Actions execution with real steps, logs, and passing required checks

GitHub Actions runner-start diagnosis is tracked in issue #61.

## Formal command

```bash
uv sync --extra full
uv run loto-hierarchicalforecast-certify
```

Expected formal success:

```text
exit_code      = 0
status         = VERIFIED
expected_cases = 40
executed_cases = 40
passed_cases   = 40
failed_cases   = 0
```

## Scope

The component covers:

- actual upstream `fit_predict()` execution
- all ten registered HierarchicalForecast reconcilers
- grouped-hierarchy compatibility and strict-tree rejection
- output shape, finite-value, and coherence validation
- deterministic four-game, ten-method certification
- exact version and module/distribution consistency evidence
- atomic runtime artifacts and portable `SHA256SUMS`
- deterministic immutable ZIP packaging and SHA-256 sidecar
- failure-phase classification and operational handoff

It does not evaluate or claim improvement in Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective
performance.

## Formal matrix

Games:

- `mini`
- `loto6`
- `loto7`
- `bingo5`

Methods expected to execute:

- `BottomUp`
- `BottomUpSparse`
- `MinTrace`
- `MinTraceSparse`
- `OptimalCombination`
- `ERM`

Methods expected to reject the grouped hierarchy before construction:

- `TopDown`
- `TopDownSparse`
- `MiddleOut`
- `MiddleOutSparse`

Total: 4 games × 10 methods = 40 formal cases. Formal seed defaults to `1`.

## Evidence package

Each run creates:

```text
artifacts/hierarchicalforecast-runtime/<run-id>/
├── RUNTIME_CERTIFICATION.json
├── METHOD_RESULTS.json
├── INPUT_EVIDENCE.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS

artifacts/hierarchicalforecast-runtime/<run-id>.zip
artifacts/hierarchicalforecast-runtime/<run-id>.zip.sha256
```

Verify with:

```bash
cd artifacts/hierarchicalforecast-runtime
sha256sum -c <run-id>.zip.sha256
unzip -t <run-id>.zip
cd <run-id>
sha256sum -c SHA256SUMS
```

## Current verification evidence

Focused evidence across separate isolated runs:

| Test group | Result |
|---|---:|
| adapter contract | 19 passed |
| ten-class state matrix | 12 passed |
| runtime certification | 9 passed |
| console entry | 2 passed |
| immutable package certification | 11 passed |
| total unique focused evidence | 53 passed |

Additional evidence:

- compileall: PASS
- manual 100-character Python line inspection: PASS
- simple secret-pattern scan: PASS
- unresolved inline review threads: 0
- Ruff: NOT_RUN in the isolated environment
- mypy: NOT_RUN in the isolated environment
- repository-wide pytest: NOT_RUN
- real installed 1.5.1 40-case execution: PENDING
- GitHub Actions: BLOCKED_RUNNER_START, issue #61

## Documentation map

| Document | Use |
|---|---|
| `REQUIREMENTS.md` | acceptance requirements and safety boundaries |
| `SPECIFICATION.md` | command, matrix, status, artifact, and package specification |
| `ARCHITECTURE.md` | components, data flow, trust boundaries, and failure isolation |
| `DATA_CONTRACT.md` | input/output invariants, shapes, determinism, and immutability |
| `TEST_PLAN.md` | focused, real-package, full-suite, and CI verification |
| `RUNTIME_CERTIFICATION.md` | runtime certification reference |
| `RUNBOOK.md` | operator execution and diagnosis procedure |
| `VERIFICATION_REPORT.md` | current evidence and readiness verdict |
| `HANDOFF.md` | next-operator commands and evidence requirements |
| `CHANGELOG.md` | branch-level change history |
| `CI_BLOCKER.md` | issue #61 diagnosis and owner checklist |
| `ARTIFACT_MANIFEST.md` | source, test, documentation, runtime, and transfer artifact inventory |

## Promotion rule

Do not mark the PR ready for review until:

- exact version 1.5.1 is installed
- formal command returns exit 0 and `VERIFIED`
- all 40 cases pass
- ZIP, sidecar, and internal SHA256SUMS verify
- Ruff and required static checks pass
- focused and repository-wide pytest pass
- issue #61 is resolved with a real-step passing Actions run
- `VERIFICATION_REPORT.md` is updated with exact evidence identifiers

No merge, auto-merge, force push, direct push to `main`, or evidence overwrite is authorized by
this document.
