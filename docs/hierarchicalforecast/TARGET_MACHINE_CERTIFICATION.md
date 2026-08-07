# HierarchicalForecast target-machine certification

## Status

`HARDENED_OPERATOR_IMPLEMENTED / ISOLATED_15_TESTS_PASS / REAL_1.5.1_EXECUTION_PENDING`

This procedure provisions the reviewed locked environment, executes the formal
HierarchicalForecast runtime certifier, and independently verifies every promoted runtime and
package claim. It uses the Python standard library before the project environment is assumed to be
usable.

It does not replace Ruff, mypy, repository-wide pytest, or GitHub Actions evidence.

## Formal command

Run from a clean checkout of the PR branch:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

`--expected-git-sha` is mandatory. The production CLI does not expose a sync-bypass option.

## Module layout

```text
scripts/run_hierarchicalforecast_target_certification.py
scripts/hierarchicalforecast_target/
├── constants.py
├── integrity.py
├── runtime_verification.py
├── package_verification.py
└── operator.py
```

Responsibilities are separated so filesystem integrity, forty-case verification, ZIP
verification, and process orchestration can be reviewed and tested independently.

## Locked execution policy

The operator executes:

```text
uv sync --extra full --locked
uv run --locked python -c <installed-version probe>
uv run --locked loto-hierarchicalforecast-certify ...
```

`--locked` prevents silent `uv.lock` changes. A stale lock, dependency conflict, or unavailable
package fails rather than changing the reviewed resolution.

The formal CLI cannot skip synchronization. The internal `skip_sync` path exists only for isolated
tests and requires `test_mode=True`.

## Git and source integrity

Formal success requires:

1. clean worktree before synchronization;
2. checked-out commit equal to `--expected-git-sha`;
3. unchanged commit and clean worktree after runtime and package verification;
4. runtime-recorded SHA-256 for:
   - `src/loto/reconciliation/runtime_certification.py`;
   - `src/loto/reconciliation/hierarchy.py`;
5. recomputed source hashes equal the recorded hashes;
6. recomputed code-set SHA-256 equal the runtime record.

A postflight change produces `FAILED_POSTFLIGHT_GIT_DRIFT` and cannot be promoted.

## Filesystem and path policy

The operator rejects:

- a symbolic-link repository root;
- symbolic-link output roots;
- symbolic-link path components inside runtime, ZIP, or sidecar paths;
- symbolic-link runtime artifacts;
- symbolic-link operator artifacts;
- paths escaping the configured evidence root;
- unsafe checksum names, parent traversal, backslashes, and duplicate checksum entries;
- unexpected runtime-directory files;
- non-regular required files.

Existing runtime evidence remains owned by the certifier's immutable Run ID policy. The operator
creates a separate Run ID and never treats a mismatched package or sidecar as success.

## Independent runtime checks

The operator does not trust the console summary alone. It independently verifies:

1. certification status `VERIFIED` and `formal_success=true`;
2. formal configuration:
   - games `mini`, `loto6`, `loto7`, `bingo5`;
   - seed `1`;
   - horizon `4`;
   - in-sample size `32`;
   - tolerance `1e-8`;
   - expected version `1.5.1`;
3. summary `expected=40`, `executed=40`, `passed=40`, `failed=0`;
4. dependency import PASS, distribution version `1.5.1`, and version consistency;
5. CPU-only device evidence and package version evidence;
6. exact runtime directory file coverage;
7. runtime `SHA256SUMS` coverage and every digest;
8. runtime artifact-manifest row count, uniqueness, coverage, byte counts, and hashes;
9. persisted certification equality with CLI output.

## Independent forty-case checks

The formal matrix must contain exactly one row for every game/method pair:

```text
4 games × 10 methods = 40 rows
```

For the 24 executable rows, the operator independently verifies:

- method identity;
- `actual_execution=true`;
- upstream version `1.5.1`;
- finite output evidence;
- exact output shape;
- finite non-negative coherence error no greater than `1e-8`;
- recorded tolerance exactly `1e-8`;
- bottom and reconciled array evidence:
  - expected shape;
  - `float64-le`;
  - finite values;
  - valid SHA-256.

For the 16 strict-tree rejections, it verifies:

- expected method identity;
- `UNSUPPORTED_HIERARCHY`;
- `actual_execution=false`;
- `hierarchy_is_strict=false`;
- non-empty rejection evidence.

It also checks that hierarchy dimensions are stable within each game and that input evidence covers
all four games with exact base, in-sample, and summing-matrix shapes.

## Independent ZIP checks

The operator verifies:

- ZIP and sidecar are regular files, not symlinks;
- exact path relationship to the runtime Run ID;
- sidecar SHA-256 equals final ZIP bytes;
- exact member coverage;
- no duplicate, traversal, encrypted, directory, or off-prefix member;
- fixed timestamp `(1980, 1, 1, 0, 0, 0)`;
- Unix regular-file mode `0644`;
- creator system `3`;
- compression method `ZIP_STORED`;
- CRC validation;
- canonical `PACKAGE_MANIFEST.json` bytes;
- exact manifest row count and uniqueness;
- every archived byte count and SHA-256;
- package content-set SHA-256;
- equality with CLI package evidence.

## Operator evidence

Every attempt writes a separate operator evidence directory:

```text
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
├── sync.stdout.log
├── sync.stderr.log
├── version.stdout.log
├── version.stderr.log
├── certification.stdout.log
├── certification.stderr.log
├── COMMANDS.json
├── OPERATOR_REPORT.json
├── ARTIFACT_MANIFEST.json
└── SHA256SUMS
```

Failure attempts retain available logs and a structured status. Runtime evidence remains under its
own Run ID in `artifacts/hierarchicalforecast-runtime/`.

## Exit policy

| Exit | Meaning |
|---:|---|
| 0 | locked provisioning, real runtime, postflight Git, and independent integrity checks passed |
| 2 | exact dependency version or formal runtime certification did not pass |
| 3 | preflight, sync, parsing, postflight Git, filesystem, source, runtime, or ZIP verification failed |

Representative operator statuses include:

- `VERIFIED`
- `FAILED_PREFLIGHT`
- `FAILED_SYNC`
- `FAILED_VERSION_MISMATCH`
- `FAILED_VERSION_PROBE`
- `FAILED_CERTIFICATION_OUTPUT`
- `FAILED_OPERATOR_VERIFICATION`
- `FAILED_POSTFLIGHT_GIT_DRIFT`
- `FAILED_OPERATOR_BOOTSTRAP`

## Isolated verification

The hardened target layer has 15 isolated tests:

- nine runtime/package verification tests;
- six operator-control tests.

They cover complete success, bad summary counts, sidecar drift, missing execution evidence, shape
drift, duplicate runtime-manifest rows, symbolic-link runtime artifacts, checksum traversal, source
hash drift, version mismatch, dirty preflight, postflight Git drift, forbidden sync bypass, and
missing expected Git SHA.

Current evidence:

```text
15 passed
compileall PASS
Python lines over 100 characters: 0
wrapper --help PASS
Ruff NOT_RUN
real HierarchicalForecast 1.5.1 execution PENDING
```

## Formal success boundary

Do not mark PR #48 ready for review until the exact current clean head produces:

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
ZIP sidecar and structure  = PASS
postflight Git             = unchanged and clean
```

The current isolated environment has not performed that real installed-package run.
