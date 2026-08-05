# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / LOCAL_P0_ORCHESTRATOR_PASS / REAL_RUNTIME_PENDING`

This directory documents the first BasicTS integration increment. It deliberately avoids the
root dependency graph, shared workers, shared catalogs, Holdout, Prospective, GPU, and DDP paths.

## Frozen upstream identity

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- isolated lane: Python 3.11

The launcher must export:

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

## P0 target-host orchestration

Run from a clean checkout of this Draft PR on a network-capable host with `git`, `uv`, and Python
available. Tracked changes must be committed before execution. An existing run directory is never
overwritten.

```bash
set -Eeuo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1

RUN_ID="basicts-p0-$(date -u +%Y%m%d-%H%M%S)"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.orchestration \
  --repo-root "${PWD}" \
  --artifacts-root "${PWD}/artifacts/basicts/p0-certification" \
  --run-id "${RUN_ID}" \
  --timeout-seconds 1800
```

The orchestrator performs the following sequence without `shell=True`:

1. records the exact Git commit and rejects tracked uncommitted changes;
2. copies the three request files into a unique run directory;
3. replaces only each copied request's `output_dir`;
4. records each request SHA-256 and seed;
5. resolves `environments/basicts-py311/uv.lock`;
6. verifies that the lock contains the frozen BasicTS revision;
7. synchronizes the isolated environment with `--frozen`;
8. proves that the isolated interpreter is Python 3.11;
9. executes `identity`, `validate_config`, and `dlinear_smoke` in order;
10. verifies all provider manifests and portable checksums;
11. writes a P0 certificate only when every required check passes;
12. writes a top-level status, manifest, command logs, and portable `SHA256SUMS`.

The provider entrypoint bootstraps the repository `src` directory itself. It therefore does not
depend on an inherited `PYTHONPATH` after the isolated process starts.

## Result verification

The command prints `BASICTS_P0_STATUS=PASS` only after certification. Use the emitted `RUN_DIR` for
independent verification:

```bash
RUN_DIR="artifacts/basicts/p0-certification/<RUN_ID>"

(
  cd "${RUN_DIR}"
  sha256sum -c SHA256SUMS
  python -m json.tool P0_RUN_STATUS.json
  python -m json.tool P0_CERTIFICATION_REPORT.json
)
```

A successful run creates at least:

- `P0_RUN_STATUS.json`
- `P0_RUN_MANIFEST.json`
- `P0_CERTIFICATION_REPORT.json`
- `P0_CERTIFICATION_REPORT.json.sha256`
- `SHA256SUMS`
- `logs/*.stdout.log`
- `logs/*.stderr.log`
- copied request files and all three provider evidence bundles

A failed phase returns exit code `2`, records `status=FAILED`, identifies `failed_phase`, retains the
failed command return code and logs, and does not create a successful certification report.

## P0 acceptance requirements

A `PASS` certificate requires all of the following:

- a non-empty isolated `uv.lock` containing the frozen BasicTS revision;
- exact BasicTS version and revision in every provider response;
- Python 3.11 in the isolated environment;
- portable `SHA256SUMS` verification with no missing, extra, or duplicate entries;
- artifact manifest file-set, size, and SHA-256 agreement;
- real allowlisted configuration imports;
- DLinear CPU fit and predict with finite state and output;
- save, strict load, and exact re-prediction equality;
- no symbolic links inside the final P0 evidence tree.

After a successful target-host run, the generated isolated `uv.lock` still requires human review
and a normal commit before this Draft PR can be considered for review. Runtime success alone does
not imply merge readiness.

## Local contract verification

This execution environment does not contain BasicTS and cannot access the external dependency
sources. The current evidence is therefore limited to local contract batches:

- existing contract and certification batch: `16 passed`;
- new orchestration and entrypoint batch: `10 passed`;
- optional real BasicTS smoke: `1 skipped`;
- compileall: `PASS`;
- 100-character line audit: `PASS`.

The skipped runtime test is not counted as success. The two local batches were run separately and
are not presented as a real BasicTS runtime result.

## Certification boundaries

This increment does not claim:

- successful dependency resolution or a reviewed `uv.lock`;
- real BasicTS 1.1.0 runtime execution;
- a target-host P0 certificate;
- BasicTS Launcher or Runner execution;
- baseline or model inventory completeness;
- TensorBoard, distributed, GPU, AMP, or DDP certification;
- chronological CV, OOF, HPO, Holdout, or Prospective results;
- accuracy improvement or baseline superiority;
- live MLflow or PostgreSQL persistence;
- shared worker or catalog integration;
- GitHub Actions success;
- merge readiness.
