# HierarchicalForecast reconciliation certification

## Status

`PARTIALLY_VERIFIED / LOCK_CONTRACT_TESTS_PASS / CI_BLOCKED_RUNNER_START / NOT_READY_FOR_REVIEW`

PR #48 replaces constructor-only availability reporting with actual upstream execution,
fail-closed validation, deterministic runtime certification, immutable evidence, and a sealed local
promotion gate.

The PR remains Draft. Local success is necessary but does not replace GitHub Actions or authorize a
ready-for-review transition.

## Formal command

Run the complete local gate on the exact fetched branch head:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Production exposes no sync, focused-test, or full-suite bypass.

Expected bounded local result:

```text
exit             = 0
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
```

## What the promotion gate verifies

1. committed `pyproject.toml` and `uv.lock` dependency contract;
2. clean expected Git commit before execution;
3. `uv sync --extra dev --extra full --locked`;
4. `uv pip check`;
5. Ruff format and lint;
6. compileall;
7. mypy over reconciliation and target modules;
8. exact focused JUnit contract of `95/0/0`;
9. repository-wide pytest with zero failures and errors;
10. installed `hierarchicalforecast==1.5.1`;
11. four games × ten methods = 40 formal runtime cases;
12. executable/rejected method partition of `24/16`;
13. runtime directory, deterministic ZIP, sidecar, and standalone package verification;
14. unchanged clean Git commit after all local stages;
15. promotion report, manifest, command logs, and `SHA256SUMS` sealing.

## Locked dependency contract

`pyproject.toml` currently declares `hierarchicalforecast>=1.0`. This range is recorded
transparently and is not treated as an exact formal pin.

Formal execution requires the committed lockfile to resolve only:

```text
hierarchicalforecast==1.5.1
```

Before provisioning, a standard-library TOML validator confirms:

- Python 3.13 is covered by project and lock ranges;
- pytest, pytest-cov, Ruff, mypy, and Pydantic are present in the dev extra;
- the full extra has exactly one HierarchicalForecast declaration;
- the lock package set contains only HierarchicalForecast 1.5.1;
- the root lock package retains HierarchicalForecast in its full extra;
- `pyproject.toml` and `uv.lock` SHA-256 values are recorded.

Target certification separately verifies the installed distribution and imported module.

## Formal runtime matrix

Games:

- `mini`
- `loto6`
- `loto7`
- `bingo5`

Expected to execute:

- `BottomUp`
- `BottomUpSparse`
- `MinTrace`
- `MinTraceSparse`
- `OptimalCombination`
- `ERM`

Expected to be rejected before construction because the project hierarchy is grouped rather than a
strict tree:

- `TopDown`
- `TopDownSparse`
- `MiddleOut`
- `MiddleOutSparse`

Formal acceptance:

```text
installed version               = 1.5.1
expected/executed/passed/failed = 40/40/40/0
actual execution rows           = 24
expected rejection rows         = 16
```

## Evidence roots

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
```

Each evidence class has its own report, command logs, manifest, and checksum root. Run IDs are
independent and must not be inferred from one another.

ZIP publication uses a hard link when supported and an `O_EXCL` no-clobber copy fallback when hard
links are unavailable, including common WSL mounted-drive cases. Existing mismatched ZIPs or
sidecars are preserved and rejected rather than overwritten.

## Current focused evidence

The following results are cumulative across separate isolated runs, not one formal combined run:

| Test group | Result |
|---|---:|
| existing reconciliation | 19 passed |
| ten-class matrix | 12 passed |
| runtime certification | 9 passed |
| console entries | 2 passed |
| immutable/portable package | 11 passed |
| standalone package verifier | 7 passed |
| target verification | 9 passed |
| target operator | 6 passed |
| hardened promotion gate | 11 passed |
| quality gate and lock drift | 9 passed |
| **Cumulative total** | **95 passed** |

Additional isolated evidence:

- compileall: PASS;
- Python lines over 100 characters: 0;
- lock 1.5.1: accepted;
- lock 1.5.0 mutation: rejected;
- remote/local Git blob equality: PASS;
- unresolved inline review threads: 0.

Not yet claimed:

- one exact-head combined 95-test run;
- formal Ruff and mypy success;
- repository-wide pytest success;
- real installed 1.5.1 execution of all 40 cases;
- real `/mnt/e` publication and standalone verification;
- formal promotion success;
- functioning GitHub Actions with actual steps and logs.

## GitHub Actions boundary

Issue #61 tracks repeated failures before runner steps are created. Current failures with
`steps=null` and no job logs are not Python test-failure evidence. Do not repeatedly rerun until an
external runner, billing, concurrency, or repository Actions condition changes.

## Accuracy boundary

This component certifies reconciliation runtime behavior and evidence integrity only. It does not
evaluate or claim improvement in Hit@±1, MAE, MSE, RMSE, position-level Hit@±1, all-position
Hit@±1, Holdout, or Prospective performance.

## Documentation map

| Document | Purpose |
|---|---|
| `REQUIREMENTS.md` | acceptance requirements and safety boundaries |
| `SPECIFICATION.md` | runtime and artifact specification |
| `ARCHITECTURE.md` | components and trust boundaries |
| `DATA_CONTRACT.md` | inputs, outputs, shapes, determinism, immutability |
| `QUALITY_GATE.md` | locked quality sequence and exact JUnit contract |
| `PROMOTION_GATE.md` | full local promotion orchestration |
| `TARGET_MACHINE_CERTIFICATION.md` | target operator contract |
| `PORTABLE_PACKAGE_PUBLICATION.md` | no-clobber publication behavior |
| `PACKAGE_VERIFIER.md` | independent transferred-package verification |
| `TEST_PLAN.md` | focused, full-suite, runtime, and CI verification |
| `RUNBOOK.md` | operator execution and diagnosis |
| `VERIFICATION_REPORT.md` | current evidence and readiness verdict |
| `HANDOFF.md` | continuation procedure |
| `ARTIFACT_MANIFEST.md` | source, test, and evidence inventory |
| `CHANGELOG.md` | branch-level change history |
| `CI_BLOCKER.md` | issue #61 evidence and owner checklist |

## Safety

- Draft retained;
- no direct push to `main`;
- no force push;
- no ready transition;
- no auto-merge;
- no merge;
- no raw evidence overwrite;
- no accuracy claim from runtime certification.
