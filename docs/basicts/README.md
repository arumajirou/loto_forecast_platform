# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / LOCAL_RECORD_INTEGRITY_CONTRACT_PASS / REAL_RUNTIME_PENDING`

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

A package version, launcher marker, or lockfile alone is not accepted as runtime identity evidence.

## Supported operations

- `identity`: verify version, revision, installed Git provenance, RECORD integrity, and import origin.
- `validate_config`: resolve only explicitly allowed serialized imports.
- `dlinear_smoke`: train the upstream DLinear module on CPU, check finite state and predictions,
  save the state dictionary, reload it, and require exact re-prediction equality.

## Installed runtime identity

Before every provider operation, the runtime requires all of these layers:

1. exact package version and launcher revision marker;
2. exact non-editable VCS provenance from `direct_url.json`;
3. RECORD SHA-256 and byte-size agreement for `direct_url.json` and
   `basicts/__init__.py`;
4. actual `basicts` import origin bound to the verified distribution file.

Missing RECORD values, file tampering, ambiguous provider mapping, shadow packages, symlinked
origins, or commit drift fail closed. See `docs/basicts/INSTALLED_PROVENANCE.md`.

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

Use `docs/basicts/FORMAL_P0_RUNBOOK.md` from a clean checkout of Draft PR #56 on a
network-capable host. The formal sequence fixes uv `0.12.0`, CPython 3.11, the BasicTS Git
revision, dependency versions, the resolution cutoff, and seed `1`.

The sequence performs:

1. isolated environment-contract verification;
2. one dependency lock and one explicit frozen synchronization;
3. structured `uv workspace metadata --locked` auditing;
4. Git and request provenance capture;
5. installed Git provenance, RECORD, import-origin, and configuration checks;
6. DLinear CPU fit, predict, save, strict load, and exact re-prediction;
7. lock immutability checks;
8. recursive manifests and portable SHA-256 evidence;
9. atomic final publication only after dependency and runtime checks pass.

Failed runs retain diagnostic evidence but never claim certification.

## Independent evidence verification

`loto.basicts_campaign.formal_verification` performs a read-only verification after the formal run.
Its report is written outside the source bundle so the original manifest and checksum set remain
unchanged.

It verifies:

- exact recursive file sets, manifests, sizes, and SHA-256 values;
- absence of symbolic links and unsafe relative paths;
- uv, Python, resolution cutoff, direct dependency, and resolved package evidence;
- preflight and core command phase order plus retained logs;
- frozen core commands and `FORMAL_PREFLIGHT_REUSE`;
- formal, preflight, core, certificate, and lock SHA-256 cross-links;
- installed Git provenance, RECORD integrity, import origin, allowlist, and DLinear evidence.

The independent report certifies retained evidence only. It does not rerun installation, training,
inference, or accuracy evaluation.

## Local contract verification

Completed as separate focused batches:

- contract and certification before provenance increments: `16 passed`;
- orchestration and entrypoint: `10 passed`;
- structured lock audit and formal wrapper: `12 passed`;
- independent formal evidence verifier: `7 passed`;
- deterministic formal receipt and symlink checks: `10 passed`;
- import-origin/runtime/certification increment: `22 passed`;
- current RECORD/runtime/certification exact-blob batch: `29 passed`;
- optional real BasicTS smoke: `1 skipped` and not counted as success;
- compileall: `PASS`;
- 100-character line audit: `PASS`.

No real target-host dependency resolution, reviewed `uv.lock`, BasicTS runtime certificate, or
merge-readiness claim is made.

## Certification boundaries

This increment does not claim:

- successful target-host dependency installation;
- a reviewed or committed isolated lockfile;
- a real formal P0 certificate;
- BasicTS Launcher or Runner execution;
- baseline or model inventory completeness;
- TensorBoard, distributed, GPU, AMP, or DDP certification;
- chronological CV, OOF, HPO, Holdout, or Prospective results;
- accuracy improvement or baseline superiority;
- live MLflow or PostgreSQL persistence;
- shared worker or catalog integration;
- GitHub Actions success;
- merge readiness.
