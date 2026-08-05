# HierarchicalForecast handoff

## Current state

- Pull request: `#48`
- Branch: `agent/hierarchicalforecast-runtime-certification`
- Base: `main`
- Status: `PARTIALLY_VERIFIED / CI_BLOCKED_RUNNER_START`
- Draft: retained
- Merge authorization: none

Resolve the exact branch head at handoff time with:

```bash
git rev-parse HEAD
```

The head SHA is intentionally not hardcoded because this document is itself part of the branch.

## What is implemented

### Reconciliation adapter

The adapter now executes upstream `fit_predict()` rather than reporting constructor availability.
It supports all ten registered HierarchicalForecast classes and records fail-closed statuses for
unavailable dependencies, unsupported grouped hierarchies, invalid options, missing in-sample
evidence, execution failures, validation failures, and verified results.

Successful executable methods must produce the expected shape, finite values, and a coherent
result within the configured tolerance.

### Runtime certification

The formal runtime harness evaluates four select-family games and ten methods for 40 cases.
Inputs are deterministic and shared fairly across methods within each game. Seed `1` is the
formal default.

### Evidence packaging

The operational console command runs certification, verifies the written artifacts, creates an
immutable deterministic ZIP, verifies the ZIP before publication, and writes a SHA-256 sidecar.
Existing packages for the same Run ID are never silently replaced.

### Documentation

- `RUNTIME_CERTIFICATION.md`: command and certification contract
- `RUNBOOK.md`: target-machine execution and failure diagnosis
- `VERIFICATION_REPORT.md`: evidence, gates, and readiness verdict
- `HANDOFF.md`: continuation instructions
- `CHANGELOG.md`: branch change summary

## Formal command

```bash
uv sync --extra full
uv run loto-hierarchicalforecast-certify
```

Diagnostic module command:

```bash
uv run python -m loto.reconciliation.runtime_certification
```

## Expected outputs

```text
artifacts/hierarchicalforecast-runtime/
├── <run-id>/
│   ├── RUNTIME_CERTIFICATION.json
│   ├── METHOD_RESULTS.json
│   ├── INPUT_EVIDENCE.json
│   ├── ARTIFACT_MANIFEST.json
│   └── SHA256SUMS
├── <run-id>.zip
└── <run-id>.zip.sha256
```

A verified ZIP contains the five run artifacts plus `PACKAGE_MANIFEST.json` under one Run ID
prefix.

## Exit codes

| Exit | Status class | Meaning |
|---:|---|---|
| 0 | `VERIFIED` | Runtime and package both passed |
| 2 | Runtime result | Dependency, version, or method matrix did not pass |
| 3 | Harness/package result | Configuration, harness, packaging, or integrity failure |

Exit-3 status values are:

- `INVALID_CONFIGURATION`
- `FAILED_CERTIFICATION_HARNESS`
- `FAILED_PACKAGING`

## Verified evidence

Focused verification currently totals 53 passed tests across separate isolated runs:

- existing reconciliation: 19
- all-method matrix: 12
- runtime certification: 9
- console entry: 2
- immutable packaging: 11

Additional checks:

- compileall: PASS
- Python maximum line length 100: PASS
- simple secret-pattern scan: PASS
- remote/local blob equality: PASS
- unresolved PR review threads: 0

Do not describe these results as one full repository pytest run.

## Remaining blockers

### Real package execution

The isolated environment could not install or load the formal target runtime. The following is
still required on the target machine:

- `hierarchicalforecast==1.5.1`
- installed console entry point
- all 40 expected cases
- command exit code 0
- verified ZIP and sidecar

### GitHub Actions

Repository CI repeatedly fails before any workflow step is created. Jobs report `steps=null` and
produce no checkout, installation, lint, compile, or pytest logs. Recheck the current head after
the runner issue is resolved.

### Static tools

No local Ruff or mypy success is claimed. Run them after the environment is available, before
changing the PR from Draft.

## Target-machine procedure

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git fetch origin
git switch agent/hierarchicalforecast-runtime-certification
git pull --ff-only

git rev-parse HEAD
uv sync --extra full

uv run python - <<'PY'
from importlib.metadata import version
resolved = version("hierarchicalforecast")
print(resolved)
raise SystemExit(0 if resolved == "1.5.1" else 2)
PY

uv run loto-hierarchicalforecast-certify
```

After a successful run:

```bash
ROOT="artifacts/hierarchicalforecast-runtime"
RUN_DIR="$(find "$ROOT" -maxdepth 1 -type d \
  -name 'hierarchicalforecast-runtime-*' -printf '%T@ %p\n' \
  | sort -nr | head -n 1 | cut -d' ' -f2-)"
RUN_ID="$(basename "$RUN_DIR")"

(
  cd "$RUN_DIR"
  sha256sum -c SHA256SUMS
)

(
  cd "$ROOT"
  sha256sum -c "$RUN_ID.zip.sha256"
  unzip -t "$RUN_ID.zip"
)
```

Read the formal summary rather than inferring success from file existence:

```bash
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
PY
```

## Required acceptance evidence

Before marking ready for review, retain:

- exact Git commit
- installed HierarchicalForecast version
- runtime Run ID
- `RUNTIME_CERTIFICATION.json`
- `METHOD_RESULTS.json`
- ZIP path and SHA-256
- passing sidecar verification
- passing archive test
- passing internal `SHA256SUMS`
- Ruff result
- mypy result where required by repository policy
- focused pytest result
- repository-wide pytest result
- GitHub Actions run with actual steps and logs

## Prohibited shortcuts

- do not mark package availability as runtime success
- do not select only the best method or successful subset
- do not relabel expected strict-tree rejection as executable success
- do not overwrite raw runtime artifacts
- do not overwrite mismatched ZIPs or sidecars
- do not delete incident evidence to obtain a green rerun
- do not claim Hit@±1 or error-metric improvement from runtime certification
- do not force push solely to reduce the GitHub Contents API commit count
- do not merge or enable auto-merge without explicit approval

## Recommended next action

Run the target-machine procedure on the exact branch head. If and only if the real 40-case matrix,
artifact verification, local quality checks, and functioning GitHub CI pass, update
`VERIFICATION_REPORT.md` with the new evidence and consider marking the PR ready for review.
