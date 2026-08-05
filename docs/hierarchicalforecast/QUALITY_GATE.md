# HierarchicalForecast local quality gate

## Status

`IMPLEMENTED / EXACT_95_TEST_CONTRACT / FORMAL_RUN_PENDING`

The quality gate runs local code-quality checks in a fixed order and preserves command, JUnit, Git,
and checksum evidence. The promotion gate subsequently re-verifies the quality report rather than
trusting its status field alone.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_quality_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Complete local sequence:

```bash
python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Production exposes no synchronization or full-suite bypass.

## Order

```text
1. clean expected Git preflight
2. uv sync --extra dev --extra full --locked
3. uv pip check
4. Ruff format --check
5. Ruff lint
6. compileall
7. mypy over reconciliation and target modules
8. focused pytest with JUnit XML
9. repository-wide pytest with JUnit XML
10. unchanged clean Git postflight
11. quality report, manifest, and SHA256SUMS sealing
```

The repository-wide suite runs only after all lighter checks and the focused suite pass.

## Exact focused contract

The focused file set includes adapter, ten-method matrix, runtime certification, console entries,
immutable package, standalone verifier, target verification, target operator, promotion gate, and
quality-gate tests.

Formal JUnit acceptance is:

```text
tests    = 95
failures = 0
errors   = 0
```

The 95 tests consist of:

| Group | Count |
|---|---:|
| existing reconciliation | 19 |
| ten-class matrix | 12 |
| runtime certification | 9 |
| console entries | 2 |
| immutable/portable package | 11 |
| standalone package verifier | 7 |
| target verification | 9 |
| target operator | 6 |
| hardened promotion gate | 11 |
| quality gate | 9 |
| **Total** | **95** |

## Evidence root

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
├── sync, dependency, Ruff, compileall, and mypy logs
├── focused_pytest logs and focused.junit.xml
├── full_pytest logs and full.junit.xml
├── COMMANDS.json
├── QUALITY_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Failure evidence is retained.

## Exit codes

| Exit | Meaning |
|---:|---|
| 0 | all quality checks, JUnit contracts, and Git postflight passed |
| 2 | a quality command or JUnit contract failed after evidence creation |
| 3 | bootstrap, preflight, path, or postflight integrity failed |

## Promotion-gate consumption

Before target certification begins, the promotion gate independently verifies:

- quality Git SHA and clean pre/post states;
- exact `95/0/0` focused JUnit totals;
- full-suite zero failures and errors;
- canonical report and manifest bytes;
- Run ID/directory identity;
- exact manifest and `SHA256SUMS` coverage and hashes.

## Current boundary

The 95 tests are cumulative isolated evidence, not yet one formal invocation. Formal Ruff, mypy,
combined focused pytest, repository-wide pytest, real HierarchicalForecast 1.5.1 certification,
and GitHub Actions remain pending.
