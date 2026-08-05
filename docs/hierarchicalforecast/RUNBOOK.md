# HierarchicalForecast certification runbook

## Purpose

Use this runbook to execute, verify, retain, and transfer the formal HierarchicalForecast
runtime evidence. This runbook certifies runtime behavior only. It does not certify forecast
accuracy or improve Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective results.

## Preconditions

Run from the repository root on the intended execution commit.

```bash
git status --short
git rev-parse HEAD
uv --version
python --version
```

The working tree should be understood before execution. The certification records the resolved
Git commit when available, but it does not silently clean or modify the working tree.

Install the full optional dependency set:

```bash
uv sync --extra full
```

Confirm the exact upstream distribution before the formal run:

```bash
uv run python - <<'PY'
from importlib.metadata import version
print(version("hierarchicalforecast"))
PY
```

The formal target is `1.5.1`. A different version is retained as evidence but returns
`FAILED_VERSION_MISMATCH`.

## Formal execution

```bash
uv run loto-hierarchicalforecast-certify
```

Expected formal matrix size:

```text
4 select-family games x 10 upstream reconcilers = 40 cases
```

The command always attempts to preserve evidence. A missing dependency or runtime failure still
produces a ZIP when the written artifacts themselves pass integrity verification.

## Exit codes

| Exit | Interpretation | Operator action |
|---:|---|---|
| 0 | Runtime and package are formally verified | Retain and transfer the ZIP plus sidecar |
| 2 | Dependency, version, or runtime certification did not pass | Inspect `RUNTIME_CERTIFICATION.json` and `METHOD_RESULTS.json`; do not promote |
| 3 | Configuration, certification harness, packaging, or integrity verification failed | Preserve all available evidence and investigate the reported phase |

Structured exit-3 statuses are:

- `INVALID_CONFIGURATION` with `phase=configuration`
- `FAILED_CERTIFICATION_HARNESS` with `phase=certification`
- `FAILED_PACKAGING` with `phase=package`

When packaging fails after certification, the JSON error retains the Run ID, run directory, and
certification status so the operator can locate the unmodified runtime evidence.

## Locate the latest result

```bash
ROOT="artifacts/hierarchicalforecast-runtime"
find "$ROOT" -maxdepth 1 -type d -name 'hierarchicalforecast-runtime-*' \
  -printf '%T@ %p\n' | sort -nr | head -n 1
find "$ROOT" -maxdepth 1 -type f -name 'hierarchicalforecast-runtime-*.zip' \
  -printf '%T@ %p\n' | sort -nr | head -n 1
```

Do not infer success from file existence alone. Read the recorded status:

```bash
RUN_DIR="<resolved-run-directory>"
uv run python - "$RUN_DIR/RUNTIME_CERTIFICATION.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "run_id": payload["run_id"],
    "status": payload["status"],
    "formal_success": payload["formal_success"],
    "summary": payload["summary"],
}, indent=2, sort_keys=True))
raise SystemExit(0 if payload["status"] == "VERIFIED" else 2)
PY
```

## Integrity verification

Verify the original run directory:

```bash
cd "$RUN_DIR"
sha256sum -c SHA256SUMS
```

Verify the ZIP sidecar and archive structure:

```bash
cd "$(dirname "$RUN_DIR")"
sha256sum -c "$(basename "$RUN_DIR").zip.sha256"
unzip -t "$(basename "$RUN_DIR").zip"
```

The archive must contain only one Run ID prefix with:

```text
RUNTIME_CERTIFICATION.json
METHOD_RESULTS.json
INPUT_EVIDENCE.json
ARTIFACT_MANIFEST.json
SHA256SUMS
PACKAGE_MANIFEST.json
```

## Immutable package behavior

The ZIP and sidecar are immutable outputs for one Run ID.

- Re-running packaging with unchanged evidence reuses the existing verified ZIP.
- If the ZIP exists but differs from deterministic package bytes, packaging fails.
- If the sidecar exists but does not match the ZIP digest, packaging fails.
- Neither a mismatched ZIP nor a mismatched sidecar is overwritten automatically.
- A temporary ZIP is verified before publication; failed temporary packages are removed.

Do not delete or replace a mismatched package merely to obtain a green rerun. Preserve it as
incident evidence, compare timestamps and hashes, and create a new certification Run ID after the
root cause is understood.

## Failure diagnosis

### `INVALID_CONFIGURATION`

Inspect the structured error and correct the requested games, seed, horizon, in-sample size,
expected version, or coherence tolerance. No formal runtime success is recorded for this attempt.

### `FAILED_CERTIFICATION_HARNESS`

The harness failed before returning a packageable certification object. Inspect the error,
Python environment, source revision, and available partial output. Do not relabel it as a runtime
or packaging pass.

### `BLOCKED_DEPENDENCY`

Inspect:

```bash
uv run python -c 'import hierarchicalforecast; print(hierarchicalforecast.__version__)'
uv pip tree | grep -i -A3 -B3 hierarchicalforecast
```

Do not relabel this as a runtime pass. Resolve installation/import errors and create a new Run ID.

### `FAILED_VERSION_MISMATCH`

Compare module and distribution evidence in `RUNTIME_CERTIFICATION.json`. Recreate the
environment from the locked dependency state and rerun. Do not overwrite the prior run.

### `FAILED_RUNTIME`

Inspect failed cases:

```bash
uv run python - "$RUN_DIR/METHOD_RESULTS.json" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for row in payload["results"]:
    if row["case_status"] != "PASS":
        print(json.dumps(row, indent=2, sort_keys=True))
PY
```

Separate expected grouped-hierarchy rejection from unexpected execution, shape, finite-value,
coherence, and exception failures.

### `FAILED_PACKAGING`

Use the retained `run_id`, `run_directory`, and `certification_status` from the structured error.
Do not use an existing, partial, or mismatched ZIP. Verify the run directory manually and compare:

- `SHA256SUMS` coverage and digests
- `ARTIFACT_MANIFEST.json` byte counts and hashes
- Run ID consistency across directory and JSON files
- existing ZIP and sidecar digests
- member timestamps, modes, paths, and storage method
- absence of renamed, missing, duplicate, or extra path entries

After correcting the root cause, run a new certification. Raw evidence and mismatched package
artifacts are never overwritten as a substitute for a new formal run.

## Evidence handoff

Transfer both files together:

```text
<run-id>.zip
<run-id>.zip.sha256
```

The receiver must run:

```bash
sha256sum -c <run-id>.zip.sha256
unzip -t <run-id>.zip
```

Record the ZIP SHA-256, Run ID, Git commit, installed HierarchicalForecast version, and final
certification status in the handoff or verification report.
