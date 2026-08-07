# HierarchicalForecast local quality gate

## Status

`IMPLEMENTED / EXACT_95_TEST_CONTRACT / LOCK_CONTRACT_ENFORCED / FORMAL_RUN_PENDING`

The quality gate runs local code-quality checks in a fixed order and preserves dependency, JUnit,
Git, command, and checksum evidence. The promotion gate consumes the resulting quality report
before target certification.

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

## Fixed order

```text
1. clean expected Git preflight
2. parse pyproject.toml and uv.lock with Python tomllib
3. require formal dev tools in the dev extra
4. require HierarchicalForecast in the full extra
5. require uv.lock to resolve only hierarchicalforecast==1.5.1
6. record pyproject.toml and uv.lock SHA-256
7. uv sync --extra dev --extra full --locked
8. uv pip check
9. Ruff format --check
10. Ruff lint
11. compileall
12. mypy over reconciliation and target modules
13. focused pytest with JUnit XML
14. repository-wide pytest with JUnit XML
15. unchanged clean Git postflight
16. quality report, manifest, and SHA256SUMS sealing
```

The repository-wide suite runs only after all lighter checks and the focused suite pass.

## Locked dependency contract

The project declaration currently remains:

```text
hierarchicalforecast>=1.0
```

Formal execution does not treat that range as sufficient. It uses `uv sync --locked` and requires
the committed lockfile to resolve exactly:

```text
locked_versions = ["1.5.1"]
formal_lock_exact = true
```

The dependency-contract report also records:

- the declaration string and whether it is itself exact;
- project and lockfile Python ranges;
- required quality-tool names;
- `pyproject.toml` SHA-256;
- `uv.lock` SHA-256.

A future lock refresh to any version other than 1.5.1 stops before environment provisioning with
`FAILED_DEPENDENCY_CONTRACT`. The broad declaration is therefore recorded transparently but cannot
silently change the formal runtime.

## Exact focused contract

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
| quality gate, including lock drift rejection | 9 |
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

`QUALITY_REPORT.json` contains the dependency-contract result and both source-file hashes. Failure
evidence is retained.

## Exit codes and statuses

| Exit | Meaning |
|---:|---|
| 0 | dependency, quality, JUnit, and Git postflight checks passed |
| 2 | a dependency, quality, or JUnit contract failed after evidence creation |
| 3 | bootstrap, preflight, path, or postflight integrity failed |

Structured dependency failure:

```text
FAILED_DEPENDENCY_CONTRACT
```

## Promotion-gate consumption

The formal promotion wrapper validates the lock contract before starting any child gate. The
quality gate then validates it again and seals the result into quality and promotion evidence.
Target certification independently verifies the installed distribution version is exactly 1.5.1.

## Current boundary

The dependency validator and the existing nine quality-gate tests passed in isolated reconstruction.
The 95 tests remain cumulative evidence, not one formal invocation. Formal Ruff, mypy, combined
focused pytest, repository-wide pytest, real HierarchicalForecast 1.5.1 certification, and usable
GitHub Actions remain pending.
