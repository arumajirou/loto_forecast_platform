# HierarchicalForecast certification runbook

## Purpose

Use this runbook to execute the complete local HierarchicalForecast promotion gate on one exact Git
commit, retain all evidence, and diagnose failures without overwriting prior runs.

This runbook certifies runtime behavior and evidence integrity. It does not certify forecast
accuracy or improve Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective results.

## Formal preconditions

- target checkout: `/mnt/e/env/ts/loto_forecast_platform-pr48`;
- branch: `agent/hierarchicalforecast-runtime-certification`;
- clean working tree;
- `uv` available;
- network access sufficient for a locked sync when dependencies are not cached;
- enough disk space for the full environment, pytest outputs, runtime evidence, and ZIP;
- GitHub Actions is a separate external gate and may remain blocked by issue #61.

Do not run the formal command from a dirty checkout or an unverified local branch tip.

## Complete formal command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48 || exit 1

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

git status --short
git rev-parse HEAD
printf 'EXPECTED_HEAD=%s\n' "${EXPECTED_HEAD}"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

The formal wrapper requires the checked-out commit to equal `EXPECTED_HEAD`. Production exposes no
flag to skip sync, focused tests, or the full repository suite.

## Execution order

```text
1. dependency-contract preflight
2. clean expected Git preflight
3. quality gate
   3.1 uv sync --extra dev --extra full --locked
   3.2 uv pip check
   3.3 Ruff format --check
   3.4 Ruff lint
   3.5 compileall
   3.6 mypy
   3.7 focused pytest with exact 95/0/0 JUnit
   3.8 repository-wide pytest with zero failures/errors
   3.9 clean unchanged Git postflight
4. target operator
   4.1 locked full environment check
   4.2 installed HierarchicalForecast version probe
   4.3 40-case runtime certification
   4.4 deterministic ZIP and sidecar publication
   4.5 independent source/runtime/package verification
5. standalone transferred-package verification
6. clean unchanged Git promotion postflight
7. promotion report, manifest, command logs, and SHA256SUMS
```

## Dependency contract

Before provisioning, the wrapper parses `pyproject.toml` and `uv.lock` with the Python standard
library. Formal execution requires:

```text
locked HierarchicalForecast versions = ["1.5.1"]
Python project/lock range             = covers 3.13
required dev tools                    = mypy, pydantic, pytest, pytest-cov, ruff
full-extra declaration count          = 1
```

`pyproject.toml` currently declares `hierarchicalforecast>=1.0`. The validator records this range
and does not misrepresent it as an exact declaration. Exact formal control comes from the committed
lockfile and the installed-version probe.

Dependency-contract failure occurs before promotion evidence is created and returns a nonzero exit.
Do not bypass it by running an unlocked install.

## Successful local result

```text
exit             = 0
status           = LOCAL_GATES_VERIFIED
formal_success   = true
ready_for_review = false
ci_required      = true
```

Required runtime summary:

```text
installed version               = 1.5.1
expected/executed/passed/failed = 40/40/40/0
actual execution rows           = 24
expected rejection rows         = 16
standalone package verifier     = VERIFIED
```

Local exit 0 does not mark the PR ready and does not replace GitHub Actions.

## Evidence roots

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
```

Do not assume these independent Run IDs are identical. Use the parent reports to follow their
recorded relationships.

### Quality evidence

```text
COMMANDS.json
QUALITY_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
focused.junit.xml
full.junit.xml
per-command stdout/stderr logs
```

### Runtime evidence

```text
RUNTIME_CERTIFICATION.json
METHOD_RESULTS.json
INPUT_EVIDENCE.json
ARTIFACT_MANIFEST.json
SHA256SUMS
```

### Operator evidence

```text
COMMANDS.json
OPERATOR_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
per-command stdout/stderr logs
```

### Promotion evidence

```text
COMMANDS.json
PROMOTION_REPORT.json
ARTIFACT_MANIFEST.json
SHA256SUMS
quality, target, and package-verifier logs
```

## Locate the latest promotion result

```bash
ROOT="artifacts/hierarchicalforecast-promotion-runs"
LATEST="$({
  find "${ROOT}" -maxdepth 1 -type d \
    -name 'hierarchicalforecast-promotion-*' \
    -printf '%T@ %p\n'
} | sort -nr | head -n 1 | cut -d' ' -f2-)"

printf 'LATEST=%s\n' "${LATEST}"
python3 - "${LATEST}/PROMOTION_REPORT.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "promotion_run_id": payload.get("promotion_run_id"),
    "status": payload.get("status"),
    "formal_success": payload.get("formal_success"),
    "ready_for_review": payload.get("ready_for_review"),
    "git_commit": payload.get("git_commit"),
    "error": payload.get("error"),
}, indent=2, sort_keys=True))
PY
```

Never infer success from the existence of a directory, ZIP, or report alone.

## Integrity verification

Verify each produced evidence directory from inside that directory:

```bash
sha256sum -c SHA256SUMS
```

Verify the runtime ZIP and sidecar:

```bash
RUNTIME_ROOT="artifacts/hierarchicalforecast-runtime"
RUN_ID="<runtime-run-id>"

(
  cd "${RUNTIME_ROOT}"
  sha256sum -c "${RUN_ID}.zip.sha256"
  unzip -t "${RUN_ID}.zip"
)
```

Use the checked-in standalone verifier rather than relying only on `unzip -t`:

```bash
uv run --locked python -m loto.reconciliation.package_verifier \
  "${RUNTIME_ROOT}/${RUN_ID}.zip"
```

The verifier must reproduce the target Run ID, ZIP path, and ZIP SHA-256 recorded by the operator.

## `/mnt/e` publication behavior

The runtime ZIP is immutable for one Run ID.

- hard-link publication is used when supported;
- when hard links are unavailable, an `O_EXCL` no-clobber copy is used;
- partial-copy failures remove the newly created partial ZIP;
- identical existing packages are verified and reused;
- differing ZIPs are preserved and rejected;
- mismatched sidecars are preserved and rejected;
- temporary ZIPs are verified before final publication.

Do not delete a mismatched artifact simply to obtain a green rerun. Retain it as incident evidence
and create a new runtime Run ID after diagnosis.

## Failure diagnosis

### `FAILED_DEPENDENCY_CONTRACT`

Inspect the reported declaration, Python ranges, required dev tools, and lockfile package rows. The
formal lock must contain only HierarchicalForecast 1.5.1. Do not use `uv sync` without `--locked` as
a workaround.

### `FAILED_SYNC`

Inspect the sync stderr log. Distinguish unavailable network or registry access from a genuine lock
resolution or wheel compatibility failure. The committed lock includes Python 3.13 artifacts, but
the target machine must still be able to retrieve or use cached packages.

### `FAILED_PIP_CHECK`

The installed environment has unsatisfied or conflicting requirements. Preserve the quality Run ID
and inspect `pip_check.stderr.log`. Do not continue to runtime certification.

### `FAILED_RUFF_FORMAT` or `FAILED_RUFF_LINT`

Use the retained command log to fix only the reported files. Re-run focused checks before the heavy
full suite. Do not describe unexecuted later stages as passing.

### `FAILED_MYPY`

Inspect the exact target modules in `COMMANDS.json`. Resolve typing errors without weakening the
formal runtime and evidence contracts.

### `FAILED_FOCUSED_TESTS`

Both command success and exact JUnit totals are required:

```text
tests=95 failures=0 errors=0
```

A changed test count is a contract failure even when pytest exits 0. Update the expected count only
when the test inventory is intentionally reviewed and documented.

### `FAILED_FULL_TESTS`

The heavy repository suite runs last. Preserve JUnit and logs, classify whether the failure is
caused by this branch, and do not promote merely because the 95 focused tests passed.

### `BLOCKED_DEPENDENCY` or `FAILED_VERSION_MISMATCH`

Inspect the operator version-probe and target logs. Formal runtime requires the installed
distribution and imported module to resolve to 1.5.1.

### `FAILED_RUNTIME`

Inspect `METHOD_RESULTS.json`. Separate expected grouped-hierarchy rejection from unexpected
construction, execution, shape, finite-value, coherence, or exception failures. All 40 rows must
reach their expected outcome.

### `FAILED_PACKAGING` or `FAILED_PACKAGE_VERIFICATION`

Inspect:

- runtime `SHA256SUMS` coverage;
- `ARTIFACT_MANIFEST.json` sizes and hashes;
- Run ID consistency;
- ZIP member paths, duplicates, timestamps, Unix modes, and compression method;
- sidecar filename and digest;
- existing ZIP/sidecar state;
- standalone verifier identity comparison.

Do not overwrite or rename mismatched evidence to force success.

### `FAILED_POSTFLIGHT_GIT_DRIFT`

The checkout changed during the gate. Retain evidence, identify the modifying process or generated
unignored file, return to a clean expected commit, and start a new formal run.

### GitHub Actions `steps=null`

Issue #61 tracks failures before runner steps are created. This is not Python test evidence. Check
repository Actions permissions, runner availability, concurrency, billing/minutes/budget, and the
GitHub status page. Avoid repeated manual reruns until an external condition changes.

## Required handoff record

Record all of the following before considering review readiness:

- exact Git commit and clean pre/post states;
- dependency-contract result and both dependency-file SHA-256 values;
- quality Run ID and focused/full JUnit totals;
- installed HierarchicalForecast version;
- runtime Run ID and 40/40/40/0 summary;
- 24/16 execution/rejection partition;
- operator Run ID;
- runtime ZIP path, byte size, publication method, and SHA-256;
- sidecar verification;
- standalone verifier result;
- promotion Run ID and `SHA256SUMS` verification;
- GitHub Actions run and job IDs with actual successful steps and logs.

## Prohibited shortcuts

- no unlocked dependency substitution;
- no dirty-worktree formal run;
- no best-method or best-seed-only certification;
- no partial 40-case acceptance;
- no evidence overwrite;
- no deletion of incident evidence to obtain success;
- no runtime-to-accuracy claim;
- no direct push to `main`;
- no force push;
- no ready transition, auto-merge, or merge without explicit approval.
