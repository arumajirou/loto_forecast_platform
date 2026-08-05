# HierarchicalForecast target-machine certification

## Status

`IMPLEMENTED / ISOLATED_TESTS_PASS / REAL_1.5.1_EXECUTION_PENDING`

This procedure provisions the locked project environment, executes the formal
HierarchicalForecast runtime certifier, and independently re-verifies the resulting runtime
artifacts and immutable ZIP.

It does not replace repository-wide Ruff, mypy, pytest, or GitHub Actions evidence.

## Formal command

From a clean checkout of the PR branch:

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The script intentionally runs before the project environment is assumed to be usable. It uses only
the Python standard library for orchestration and evidence verification.

## Locked environment policy

The runner executes:

```text
uv sync --extra full --locked
uv run --locked python -c <installed-version check>
uv run --locked loto-hierarchicalforecast-certify ...
```

`--locked` prevents the operator command from silently updating `uv.lock`. A stale or incompatible
lock fails the run rather than changing the reviewed dependency resolution.

Formal execution also requires a clean Git worktree. Untracked or modified files outside ignored
runtime directories produce `FAILED_PREFLIGHT`.

## Independent checks

The operator runner does not accept the console command's summary alone. It independently checks:

1. the checked-out Git commit and optional expected head SHA;
2. installed `hierarchicalforecast` version exactly `1.5.1`;
3. certification command exit code zero;
4. overall status `VERIFIED` and `formal_success=true`;
5. summary counts `expected=40`, `executed=40`, `passed=40`, `failed=0`;
6. exact-version and module/distribution consistency flags;
7. persisted runtime certification equals the CLI certification object;
8. `SHA256SUMS` coverage and every runtime artifact digest;
9. runtime artifact-manifest file coverage, byte counts, and SHA-256 values;
10. all 40 unique game/method rows in `METHOD_RESULTS.json`;
11. 24 executable cases with `actual_execution=true`;
12. 16 grouped-hierarchy rejections with `actual_execution=false`;
13. all per-case checks true and expected/observed statuses equal;
14. all four games present in `INPUT_EVIDENCE.json`;
15. ZIP path and sidecar relationship;
16. ZIP sidecar digest against the final archive bytes;
17. exact ZIP member coverage and no duplicates or traversal;
18. fixed ZIP timestamp, Unix file mode, creator system, and `ZIP_STORED` method;
19. canonical `PACKAGE_MANIFEST.json` bytes;
20. every archived member's byte count and SHA-256;
21. package content-set SHA-256 and CLI package evidence.

Any mismatch fails closed and is not promoted to formal success.

## Operator evidence

Every invocation writes a separate operator run directory:

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

When execution stops before a command, only the evidence available up to that phase is included.
The operator directory is still created and receives a structured failure report when filesystem
publication remains possible.

The existing runtime certifier separately creates:

```text
artifacts/hierarchicalforecast-runtime/<run-id>/
artifacts/hierarchicalforecast-runtime/<run-id>.zip
artifacts/hierarchicalforecast-runtime/<run-id>.zip.sha256
```

Operator evidence and runtime evidence have separate Run IDs and checksum roots.

## Exit policy

| Exit | Meaning |
|---:|---|
| `0` | target-machine runner and formal runtime/package verification passed |
| `2` | dependency, exact-version, or formal runtime certification did not pass |
| `3` | preflight, locked sync, command-output, or independent integrity verification failed |

Use `OPERATOR_REPORT.json` as the primary operator verdict. Do not infer success only from the
presence of a ZIP.

## Expected success report

A formal success contains at least:

```text
status = VERIFIED
formal_success = true
installed_version = 1.5.1
summary.expected_cases = 40
summary.executed_cases = 40
summary.passed_cases = 40
summary.failed_cases = 0
method_partition.executed_cases = 24
method_partition.rejected_cases = 16
```

## Verification of operator evidence

```bash
OPERATOR_DIR="$(find artifacts/hierarchicalforecast-target-runs \
  -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -n \
  | tail -1 \
  | cut -d' ' -f2-)"

(
  cd "${OPERATOR_DIR}"
  sha256sum -c SHA256SUMS
)

python3 - "${OPERATOR_DIR}/OPERATOR_REPORT.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
assert report["status"] == "VERIFIED", report
assert report["formal_success"] is True, report
PY
```

## Diagnostic options

Skip environment synchronization only when the reviewed locked environment has already been
provisioned:

```bash
python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "$(git rev-parse HEAD)" \
  --skip-sync
```

`--skip-sync` still uses `uv run --locked`, checks the exact installed version, and performs all
runtime and package verification. It does not permit a dirty worktree.

Alternative output roots may be supplied with:

```text
--output-root
--operator-root
```

## Local isolated verification

The target-machine runner test file covers:

- complete successful runtime and ZIP bundle;
- incorrect 40-case count;
- ZIP sidecar mismatch;
- removed actual-execution evidence;
- checksum path traversal;
- successful operator orchestration and evidence publication;
- exact-version mismatch with retained evidence;
- dirty-worktree preflight failure.

Result: **8 passed**.

Remote/local Git blob equality was verified for the runner and its tests before this document was
published. Python compileall passed, and both files contain no lines longer than 100 characters.

## Promotion boundary

Passing this target-machine command resolves the real HierarchicalForecast 1.5.1 runtime gate only.
PR #48 must remain Draft until issue #61 is also resolved with a GitHub Actions run that contains
real checkout, install, Ruff, compileall, and pytest steps and passing required checks.

Do not overwrite mismatched evidence, force-push the branch, mark the PR ready, or merge solely
because the operator command created artifacts.
