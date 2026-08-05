# HierarchicalForecast artifact manifest

## Status

- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- State: `PARTIALLY_VERIFIED / LOCK_CONTRACT_TESTS_PASS / CI_BLOCKED_PRE_RUN`
- Canonical repository CI blocker: issue #58
- PR-specific CI dependency: issue #61

Machine-generated manifests and checksum files are the integrity roots. Documentation describes
them but does not replace them.

## Source implementation

| Path | Role |
|---|---|
| `src/loto/reconciliation/hierarchy.py` | upstream execution and validation adapter |
| `src/loto/reconciliation/runtime_certification.py` | deterministic 40-case certification |
| `src/loto/reconciliation/package_certification.py` | runtime package construction and validation |
| `src/loto/reconciliation/portable_package_certification.py` | no-clobber publication |
| `src/loto/reconciliation/package_verifier.py` | read-only transferred-package verifier |
| `scripts/hierarchicalforecast_target/dependency_contract.py` | TOML lock and tool contract validation |
| `scripts/hierarchicalforecast_target/integrity.py` | path, JSON, SHA, and array helpers |
| `scripts/hierarchicalforecast_target/runtime_verification.py` | independent 40-row verification |
| `scripts/hierarchicalforecast_target/package_verification.py` | source, ZIP, sidecar, and manifest checks |
| `scripts/hierarchicalforecast_target/operator.py` | target orchestration and explicit Git evidence |
| `scripts/hierarchicalforecast_target/quality_gate.py` | lock, quality, and exact 95-test gate |
| `scripts/hierarchicalforecast_target/promotion_gate.py` | cross-root semantic and integrity verification |
| `scripts/run_hierarchicalforecast_target_certification.py` | target wrapper |
| `scripts/run_hierarchicalforecast_quality_gate.py` | quality wrapper |
| `scripts/run_hierarchicalforecast_promotion_gate.py` | lock-preflight and full promotion wrapper |

## Checked-in dependency roots

The formal dependency preflight hashes and verifies:

```text
pyproject.toml
uv.lock
```

The declaration currently allows `hierarchicalforecast>=1.0`, while the formal locked resolution
must be exactly `hierarchicalforecast==1.5.1`. The report records the declaration, exactness flag,
resolved versions, Python ranges, required dev-tool set, and both SHA-256 values.

## Test inventory

| Group | Count |
|---|---:|
| existing reconciliation | 19 |
| ten-class matrix | 12 |
| runtime certification | 9 |
| console entries | 2 |
| immutable/portable package | 11 |
| standalone verifier | 7 |
| target verification | 9 |
| target operator | 6 |
| hardened promotion gate | 11 |
| quality gate, including lock drift rejection | 9 |
| **Cumulative focused evidence** | **95** |

The 95 results are cumulative isolated evidence. One formal combined run remains pending.

## Integrity roots

| Evidence class | Integrity root |
|---|---|
| checked-in source/docs/dependency files | exact Git commit |
| runtime directory | runtime `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| transfer ZIP | `<runtime-run-id>.zip.sha256` plus internal manifests |
| target operator | operator `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| local quality | quality `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |
| local promotion | promotion `ARTIFACT_MANIFEST.json` and `SHA256SUMS` |

Run IDs are independent. Promotion evidence cross-checks but does not replace the other roots.

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

## Operator evidence

```text
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
├── command logs
├── COMMANDS.json
├── OPERATOR_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

`OPERATOR_REPORT.json` records `expected_git_sha`, explicit `git_commit`, clean preflight and
postflight states, installed version, runtime result, and verification checks.

## Quality evidence

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
├── dependency, Ruff, compileall, mypy, and pytest logs
├── focused.junit.xml
├── full.junit.xml
├── COMMANDS.json
├── QUALITY_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

`QUALITY_REPORT.json` includes the dependency-contract result and the `pyproject.toml` and `uv.lock`
SHA-256 values. Focused JUnit must be exactly `95/0/0`; full JUnit must have zero failures and
errors.

## Promotion evidence

```text
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
├── quality, target, and verifier logs
├── COMMANDS.json
├── PROMOTION_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Promotion verification confirms child Git identity, JUnit totals, version 1.5.1, 40-case totals,
24/16 method partition, canonical report/manifest identity, checksum coverage, and ZIP identity.
The formal promotion wrapper additionally rejects a non-1.5.1 lock before creating a promotion Run
ID.

## Formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

## Pending artifacts

- formal promotion evidence for the current reviewed head;
- formal dependency-contract output against the actual checked-out files;
- formal Ruff, mypy, combined 95-test, and full-pytest evidence;
- real HierarchicalForecast 1.5.1 40-case runtime bundle;
- real `/mnt/e` publication and standalone re-verification;
- GitHub Actions logs with real passing steps.

Issue #58 is the canonical repository-wide CI blocker. Issue #61 records PR #48's dependency on
that blocker. Never overwrite evidence directories, mismatched ZIPs, or mismatched sidecars;
preserve them and create a new Run ID.
