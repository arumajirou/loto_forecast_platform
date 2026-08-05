# HierarchicalForecast verification report

## Report status

- Component: HierarchicalForecast reconciliation adapter, runtime certification, immutable package,
  and hardened target-machine operator
- Pull request: #48
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Verification state:
  `PARTIALLY_VERIFIED / HARDENED_OPERATOR_TESTS_PASS / CI_BLOCKED_RUNNER_START`
- Formal promotion state: `NOT_READY_FOR_REVIEW`

The branch must remain Draft until a real installed `hierarchicalforecast==1.5.1` run and repository
CI both produce usable passing evidence.

## Scope

This report covers:

- upstream `fit_predict()` execution through the adapter;
- all ten registered reconciliation classes;
- grouped-hierarchy compatibility and strict-tree rejection;
- shape, finite-value, and coherence validation;
- deterministic 40-case runtime orchestration;
- runtime artifact manifests and SHA-256;
- deterministic immutable ZIP and sidecar;
- target-machine locked provisioning;
- independent runtime, case, source, filesystem, and package verification;
- preflight and postflight Git integrity;
- structured failure states and focused tests.

This work does not evaluate or claim improvement in Hit@±1, MAE, MSE, RMSE, Holdout, or
Prospective performance.

## Formal matrix

The default certification uses:

- games: `mini`, `loto6`, `loto7`, `bingo5`;
- methods: ten registered HierarchicalForecast reconcilers;
- seed: `1`;
- horizon: `4`;
- in-sample size: `32`;
- coherence tolerance: `1e-8`;
- total: 40 cases.

Expected executable methods:

- `BottomUp`
- `BottomUpSparse`
- `MinTrace`
- `MinTraceSparse`
- `OptimalCombination`
- `ERM`

Expected grouped-hierarchy rejections:

- `TopDown`
- `TopDownSparse`
- `MiddleOut`
- `MiddleOutSparse`

## Evidence reviewed

### Adapter contract

`VERIFIED_WITH_DETERMINISTIC_TEST_DOUBLES`

- executable methods call `fit_predict()`;
- sparse methods receive CSR;
- ERM receives paired in-sample arrays;
- constructor and execution errors fail closed;
- result shape, finite values, and coherence are checked;
- strict-tree methods are rejected before execution for the grouped hierarchy.

### Runtime-certification contract

`VERIFIED_WITH_DETERMINISTIC_TEST_DOUBLES`

- all 40 rows are retained;
- one case exception does not abort remaining cases;
- dependency, version, runtime, and blocked states remain distinct;
- runtime JSON, manifest, and `SHA256SUMS` are written atomically;
- runtime source, environment, Git, device, and package evidence is recorded.

### Immutable-package contract

`VERIFIED`

- required runtime coverage and checksums are verified;
- unsafe paths and duplicates are rejected;
- package-manifest bytes are canonical;
- ZIP metadata and order are deterministic;
- temporary ZIP verification occurs before publication;
- identical existing packages may be reused;
- differing ZIPs or sidecars are preserved and rejected.

### Hardened target-machine operator

`VERIFIED_WITH_SYNTHETIC_SEALED_EVIDENCE`

The target operator now independently verifies rather than trusting the CLI summary. Hardening
confirmed in the reviewed implementation includes:

- mandatory expected Git SHA;
- no production sync-bypass option;
- locked synchronization and execution;
- clean and unchanged Git state before and after certification;
- rejection of symbolic-link roots, path components, runtime files, package files, and operator
  files;
- exact runtime directory and manifest coverage;
- duplicate manifest-row rejection;
- independent 40-case game/method partition;
- independent shape, finite, coherence, and array-hash evidence checks;
- exact formal configuration evidence;
- exact dependency and CPU-device evidence;
- recomputation of `hierarchy.py` and `runtime_certification.py` source SHA-256;
- recomputation of runtime code-set SHA-256;
- independent ZIP metadata, manifest, member, and sidecar verification;
- separate operator evidence Run ID and SHA manifest.

## Focused test evidence

The totals below are the sum of separate isolated runs, not one repository-wide pytest invocation.

| Test group | Result |
|---|---:|
| Existing reconciliation tests | 19 passed |
| Ten-class upstream-state matrix | 12 passed |
| Runtime-certification tests | 9 passed |
| Console-entry tests | 2 passed |
| Immutable package-certification tests | 11 passed |
| Hardened target verification tests | 9 passed |
| Hardened target operator tests | 6 passed |
| **Total unique focused evidence** | **68 passed** |

The new 15-test target batch was also executed together against an exact local reconstruction of
the published Git blobs:

```text
15 passed
```

## Static and transfer checks

- Python compileall for the hardened target files: `PASS`
- Python lines over 100 characters in the hardened target files: `0`
- target wrapper `--help`: `PASS`
- required `--expected-git-sha` visible in the CLI: `PASS`
- remote/local Git blob equality for all ten hardened target files: `PASS`
- Ruff: `NOT_RUN`; Ruff was not installed or cached
- mypy: `NOT_RUN`
- repository-wide pytest: `NOT_RUN`

## Security-review findings resolved

The third-party review identified and corrected the following risks:

1. no postflight Git recheck;
2. symbolic-link runtime artifacts accepted as regular files;
3. duplicate runtime-manifest rows not explicitly rejected;
4. executable case records trusted through aggregate checks without independent shape, finite,
   coherence, and array-evidence validation;
5. production CLI allowed synchronization bypass;
6. expected Git SHA was optional;
7. runtime-recorded source hashes were not recomputed by the operator;
8. monolithic runner mixed process, filesystem, runtime, and package responsibilities.

All are covered by the current split implementation and focused tests.

## Upstream contract evidence

Nixtla v1.5.1 source inspection previously confirmed the expected API-level behavior for MinTrace,
TopDown, MiddleOut, ERM, grouped hierarchies, sparse variants, and `mean` output handling. Source
inspection is not a substitute for the still-pending installed-package execution.

## GitHub review state

- unresolved inline review threads: `0` at the latest review audit;
- human approval: none;
- requested changes: none;
- GitHub reports the PR mergeable;
- the PR remains Draft.

## GitHub Actions state

`BLOCKED_RUNNER_START`, tracked by issue #61.

The latest previously inspected head completed its CI job as failure with `steps=null` and no job
log. Checkout, setup, dependency installation, Ruff, compileall, and pytest did not execute. This is
not accepted as Python test-failure evidence, but it provides no CI verification.

The final hardened head must be inspected once GitHub creates its automatic run. Do not manually
rerun repeatedly while the external condition remains unchanged.

## Promotion gates

| Gate | State | Required evidence |
|---|---|---|
| Adapter execution contract | PASS with test doubles | focused adapter tests |
| Ten-class state partition | PASS | complete matrix tests |
| Runtime orchestration | PASS with test doubles | deterministic runtime tests |
| Immutable evidence package | PASS | corruption and immutability tests |
| Hardened target operator | PASS with synthetic sealed evidence | 15 focused tests |
| Real package runtime | PENDING | exact 1.5.1, 40/40, 24 executions, 16 rejections |
| Ruff and supported typing | PENDING | exact commands and results |
| Combined focused suite | PENDING | one recorded invocation |
| Repository-wide pytest | PENDING | one classified full run |
| GitHub Actions | BLOCKED | real steps, logs, and passing checks |
| Forecast accuracy | NOT_APPLICABLE | separate chronological experiment |

## Formal target command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Formal acceptance requires:

```text
operator exit             = 0
operator status           = VERIFIED
runtime status            = VERIFIED
expected/executed/passed  = 40/40/40
failed                     = 0
actual executions          = 24
grouped rejections         = 16
runtime SHA256SUMS         = PASS
operator SHA256SUMS        = PASS
ZIP and sidecar            = PASS
preflight/postflight Git   = same clean commit
```

## Final verdict

`NOT_READY_FOR_REVIEW`

The implementation is ready for target-machine execution, but formal promotion remains blocked by:

- real installed HierarchicalForecast 1.5.1 execution;
- Ruff, supported typing, combined focused, and full pytest evidence;
- GitHub Actions with actual runner steps and passing checks.

No merge, auto-merge, ready transition, force push, or direct push to `main` is authorized by this
report.
