# BasicTS isolated provider contract

Status: `PARTIALLY_VERIFIED / LOCAL_INSTALLED_PROVENANCE_CONTRACT_PASS / REAL_RUNTIME_PENDING`

This directory documents the first BasicTS integration increment. It deliberately avoids the
root dependency graph, shared workers, shared catalogs, Holdout, Prospective, GPU, and DDP paths.

## Frozen upstream identity

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- isolated lane: Python 3.11

The launcher exports the expected revision marker, but the marker alone is not accepted as installed
package provenance. Every provider operation also reads the installed `BasicTS` distribution's
`direct_url.json` through `importlib.metadata`.

PASS requires:

- distribution name `BasicTS` and version `1.1.0`;
- repository `https://github.com/GestaltCogTeam/BasicTS`;
- VCS `git`;
- exact `commit_id` and `requested_revision` equal to the frozen revision;
- a non-editable VCS installation with no archive, local-directory, or subdirectory substitution.

The identity bundle retains these fields plus a SHA-256 of the raw `direct_url.json` text. Missing,
malformed, editable, non-Git, wrong-repository, wrong-version, or wrong-revision provenance fails
closed before identity, configuration, or DLinear work can pass.

## Supported operations

- `identity`: verify exact package version, revision marker, and installed Git provenance.
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

Use `docs/basicts/FORMAL_P0_RUNBOOK.md` from a clean checkout of Draft PR #56 on a
network-capable host. The formal sequence fixes uv `0.12.0`, CPython 3.11, the BasicTS Git
revision, dependency versions, the resolution cutoff, and seed `1`.

The sequence performs:

1. isolated environment-contract verification;
2. one dependency lock and one explicit frozen synchronization;
3. structured `uv workspace metadata --locked` auditing;
4. Git and request provenance capture;
5. installed-distribution `direct_url.json` provenance verification;
6. identity and configuration allowlist checks;
7. DLinear CPU fit, predict, save, strict load, and exact re-prediction;
8. lock immutability checks;
9. recursive manifests and portable SHA-256 evidence;
10. atomic final publication only after dependency and runtime checks pass.

Failed runs retain diagnostic evidence but never claim certification.

## Independent evidence and receipt verification

`loto.basicts_campaign.formal_verification` performs a read-only verification after the formal run.
It verifies exact file sets, manifests, SHA-256, dependency metadata, command order, frozen model
commands, lock cross-links, installed Git provenance, import allowlisting, and DLinear evidence.

`loto.basicts_campaign.formal_receipt` then creates a deterministic receipt outside the source
bundle. The receipt binds the complete checksum map and verification report to an explicitly
captured Git commit and can be recomputed later to detect source or receipt drift.

These layers certify retained evidence only. They do not rerun installation, training, inference,
or accuracy evaluation and are not cryptographic signing or an external timestamp authority.

## Local contract verification

The current execution environment cannot install the real upstream BasicTS dependency. Evidence is
therefore separated into focused batches:

- contract and certification: `16 passed` before the provenance increment;
- orchestration and entrypoint: `10 passed`;
- structured lock audit and formal wrapper: `12 passed`;
- independent formal evidence verifier: `7 passed`;
- deterministic formal receipt and symlink checks: `10 passed`;
- installed provenance, runtime integration, and certification: `15 passed`;
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
- cryptographic signing or external timestamping;
- merge readiness.
