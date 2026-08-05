# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / LOCAL_FORMAL_P0_CONTRACT_PASS / REAL_RUNTIME_PENDING`

This directory documents the first BasicTS integration increment. It deliberately avoids the
root dependency graph, shared workers, shared catalogs, Holdout, Prospective, GPU, and DDP paths.

## Frozen upstream identity

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- isolated lane: CPython 3.11
- uv version: `0.12.0`
- resolution cutoff: `2026-08-05T00:00:00Z`

The fixed upstream requirements include `easy-torch==1.3.3`, `numpy==1.24.4`,
`setuptools==59.5.0`, and `transformers==4.40.1`. The isolated environment keeps those
compatibility-sensitive versions separate from the root project.

The provider must receive:

```bash
export BASICTS_UPSTREAM_REVISION=c2bb6e31e591167e84459775a21a62e70a5893ce
```

A package version alone is not accepted as revision evidence.

## Supported operations

- `identity`: verify exact version and revision marker.
- `validate_config`: resolve only explicitly allowed serialized imports.
- `dlinear_smoke`: train the upstream DLinear module on CPU, check finite state and predictions,
  save the state dictionary, reload it, and require exact re-prediction equality.

## Security boundary

Serialized configuration references are restricted to:

- `basicts.*`
- `loto.adapters.basicts.*`
- `torch.optim.*`
- `torch.optim.lr_scheduler.*`

Unknown keys and non-allowlisted imports fail closed.

## Data and metric contracts

`GameGeometry` preserves game ID, ordered position columns, legal value range, draw number, and
optional draw date. Input is never silently sorted, deduplicated, filled, or repaired.

Hit@±1 is the primary metric. MAE, MSE, RMSE, position-wise Hit@±1, and all-position Hit@±1 are
retained.

## Formal P0 target-host orchestration

Run from a clean checkout of this Draft PR on a network-capable host with `git`, uv `0.12.0`, and
Python available. Tracked changes must be committed before execution. Existing formal and staging
directories are never overwritten.

```bash
set -Eeuo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1

uv --version

RUN_ID="basicts-formal-p0-$(date -u +%Y%m%d-%H%M%S)"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_orchestration \
  --repo-root "${PWD}" \
  --artifacts-root "${PWD}/artifacts/basicts/formal-p0" \
  --run-id "${RUN_ID}" \
  --timeout-seconds 1800
```

The formal orchestrator first runs an immutable dependency-resolution preflight:

1. verifies the isolated `pyproject.toml` direct dependency contract;
2. requires uv `0.12.0`;
3. resolves with CPython 3.11 and the configured `exclude-newer` cutoff;
4. runs `uv lock --check`;
5. runs `uv sync --frozen`;
6. captures `uv workspace metadata --locked` as JSON;
7. rejects workspace conflicts and a non-CPython or non-3.11 environment;
8. verifies the BasicTS Git repository, exact commit, and package version;
9. verifies exact resolved versions for BasicTS, easy-torch, numpy, setuptools, torch, and
   transformers;
10. records the environment input SHA-256, lock SHA-256, metadata SHA-256, commands, and logs.

Only after preflight PASS does it run the existing P0 sequence:

1. records the exact Git commit and rejects tracked uncommitted changes;
2. copies the three request files into a unique core run directory;
3. replaces only each copied request's `output_dir`;
4. records each request SHA-256 and seed;
5. proves that the isolated interpreter is Python 3.11;
6. executes `identity`, `validate_config`, and `dlinear_smoke` in order;
7. verifies all provider manifests and portable checksums;
8. writes a core P0 certificate only when every required check passes.

The formal wrapper then verifies that `uv.lock` did not change between preflight and core P0. It
publishes the staging directory atomically only when both parts pass. A failed formal run is also
published as a diagnostic bundle, but it records `status=FAILED` and never claims certification.

The provider entrypoint bootstraps the repository `src` directory itself. It therefore does not
depend on an inherited `PYTHONPATH` after the isolated process starts.

## Formal result verification

The command prints `BASICTS_FORMAL_P0_STATUS=PASS` only after dependency and runtime certification.
Use the emitted `RUN_DIR` for independent verification:

```bash
RUN_DIR="artifacts/basicts/formal-p0/<RUN_ID>"

(
  cd "${RUN_DIR}"
  sha256sum -c SHA256SUMS
  python -m json.tool FORMAL_P0_STATUS.json
  python -m json.tool preflight/UV_RESOLUTION_AUDIT.json
  python -m json.tool core/P0_RUN_STATUS.json
  python -m json.tool core/P0_CERTIFICATION_REPORT.json
)
```

A successful formal run creates at least:

- `FORMAL_P0_STATUS.json`
- `FORMAL_P0_MANIFEST.json`
- `SHA256SUMS`
- `preflight/UV_WORKSPACE_METADATA.json`
- `preflight/UV_RESOLUTION_AUDIT.json`
- `preflight/UV_RESOLUTION_AUDIT.json.sha256`
- `preflight/logs/*.stdout.log`
- `preflight/logs/*.stderr.log`
- `core/P0_RUN_STATUS.json`
- `core/P0_RUN_MANIFEST.json`
- `core/P0_CERTIFICATION_REPORT.json`
- `core/P0_CERTIFICATION_REPORT.json.sha256`
- all three provider evidence bundles

A failed phase returns exit code `2`, records `status=FAILED`, identifies `failed_phase`, retains
available command return codes and logs, and does not create a successful formal certificate.

## Formal P0 acceptance requirements

Formal PASS requires all of the following:

- exact isolated direct dependency inputs;
- uv `0.12.0` and the fixed resolution cutoff;
- an up-to-date, non-empty `uv.lock`;
- structured workspace metadata with no conflicts;
- BasicTS `1.1.0` from the exact frozen Git commit;
- easy-torch `1.3.3`;
- numpy `1.24.4`;
- setuptools `59.5.0`;
- torch `2.9.1`;
- transformers `4.40.1`;
- CPython 3.11 in the isolated environment;
- exact BasicTS version and revision in every provider response;
- portable `SHA256SUMS` verification with no missing, extra, or duplicate entries;
- artifact manifest file-set, size, and SHA-256 agreement;
- real allowlisted configuration imports;
- DLinear CPU fit and predict with finite state and output;
- save, strict load, and exact re-prediction equality;
- no symbolic links inside the final formal evidence tree;
- unchanged `uv.lock` between resolution audit and core runtime.

After a successful target-host run, the generated isolated `uv.lock` still requires human review
and a normal commit before this Draft PR can be considered for review. Runtime success alone does
not imply merge readiness.

## Local contract verification

This execution environment does not contain BasicTS and cannot access the external dependency
sources. The current evidence is therefore limited to local contract batches:

- existing contract and certification batch: `16 passed`;
- orchestration and entrypoint batch: `10 passed`;
- structured lock audit and formal wrapper batch: `12 passed`;
- optional real BasicTS smoke: `1 skipped`;
- compileall: `PASS`;
- 100-character line audit: `PASS`.

The skipped runtime test is not counted as success. The local batches were run separately and are
not presented as a real BasicTS runtime result.

## Certification boundaries

This increment does not claim:

- successful target-host dependency resolution;
- a reviewed or committed isolated `uv.lock`;
- real BasicTS 1.1.0 runtime execution;
- a target-host formal P0 certificate;
- BasicTS Launcher or Runner execution;
- baseline or model inventory completeness;
- TensorBoard, distributed, GPU, AMP, or DDP certification;
- chronological CV, OOF, HPO, Holdout, or Prospective results;
- accuracy improvement or baseline superiority;
- live MLflow or PostgreSQL persistence;
- shared worker or catalog integration;
- GitHub Actions success;
- merge readiness.
