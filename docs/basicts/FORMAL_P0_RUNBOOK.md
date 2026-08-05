# BasicTS formal P0 runbook

Status: `TARGET_HOST_EXECUTION_PENDING`

This runbook executes the isolated BasicTS dependency audit and DLinear CPU certification without
modifying the root dependency graph or shared runtime paths.

## Frozen inputs

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- upstream revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- Python lane: CPython 3.11
- uv version: `0.12.0`
- resolution cutoff: `2026-08-05T00:00:00Z`
- seed: `1`

`uv workspace metadata` currently exposes a preview JSON schema. The formal audit therefore pins
the uv version and stores the complete metadata JSON, canonical audit JSON, command logs, and
SHA-256 values. Do not substitute a different uv version without updating and reviewing the schema
contract and focused tests.

## Preconditions

Run from a clean checkout of Draft PR #56 on a network-capable Linux host.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git rev-parse HEAD
uv --version
python --version
```

Required before execution:

- tracked repository files are clean;
- `uv --version` reports exactly `uv 0.12.0`;
- Python can start the repository module using `PYTHONPATH=${PWD}/src`;
- the host can reach the Python package and Git sources;
- the final Run ID does not already exist.

## Execute

```bash
set -Eeuo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1

RUN_ID="basicts-formal-p0-$(date -u +%Y%m%d-%H%M%S)"
ARTIFACTS_ROOT="${PWD}/artifacts/basicts/formal-p0"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_orchestration \
  --repo-root "${PWD}" \
  --artifacts-root "${ARTIFACTS_ROOT}" \
  --run-id "${RUN_ID}" \
  --timeout-seconds 1800
```

The formal preflight performs one dependency resolution and one explicit frozen synchronization.
The nested core P0 validates the preflight lock SHA-256 and reuses that environment. It does not run
another `uv lock` or explicit `uv sync`. Every core `uv run` uses `--frozen`; uv may check or
synchronize the already prepared environment, but it cannot update the lockfile silently. The core
also verifies the lock SHA-256 again before certification.

## Expected PASS output

The command must print both lines:

```text
BASICTS_FORMAL_P0_STATUS=PASS
RUN_DIR=<absolute path>
```

The final directory is published atomically only after dependency and runtime certification pass.
A failed run returns exit code `2` and retains a diagnostic bundle with `status=FAILED`.

## Independent verification

```bash
RUN_DIR="${ARTIFACTS_ROOT}/${RUN_ID}"

(
  cd "${RUN_DIR}"
  sha256sum -c SHA256SUMS
  python -m json.tool FORMAL_P0_STATUS.json
  python -m json.tool FORMAL_P0_MANIFEST.json
  python -m json.tool preflight/UV_RESOLUTION_AUDIT.json
  python -m json.tool core/P0_RUN_STATUS.json
  python -m json.tool core/P0_CERTIFICATION_REPORT.json
)

(
  cd "${RUN_DIR}/preflight"
  sha256sum -c UV_RESOLUTION_AUDIT.json.sha256
)

(
  cd "${RUN_DIR}/core"
  sha256sum -c SHA256SUMS
  sha256sum -c P0_CERTIFICATION_REPORT.json.sha256
)
```

PASS requires all checksum commands to succeed and all three status documents to report `PASS`.

## Mandatory review before promotion

Review at least:

- exact Git commit in the core status;
- uv version and resolution cutoff;
- BasicTS Git source, version, and revision;
- resolved versions of easy-torch, numpy, setuptools, torch, and transformers;
- CPython implementation and 3.11 version;
- absence of workspace conflicts;
- DLinear input, target, and prediction shapes;
- finite losses, model state, and predictions;
- CPU device and no CPU fallback claim;
- strict save/load and exact re-prediction equality;
- request SHA-256 and seed values;
- top-level and nested manifests.

After review, commit `environments/basicts-py311/uv.lock` normally. Do not force-push, rewrite
history, enable auto-merge, or promote the Draft PR solely because the formal P0 command returned
PASS.

## Failure handling

Use `FORMAL_P0_STATUS.json` and the recorded `failed_phase` first. Then inspect the matching files
under `preflight/logs/` or `core/logs/`. Do not repeatedly rerun an unchanged failure. Preserve the
failed bundle for comparison with the next Run ID.

A failure in dependency resolution, identity, import allowlisting, DLinear execution, persistence,
re-prediction, finite-value checks, shape checks, or SHA-256 verification is a formal failure. It
must not be converted to PASS manually.
