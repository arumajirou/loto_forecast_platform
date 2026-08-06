# Requirements

## Functional requirements

1. Every record fixes a logical model ID, paper identity, source/model repository identity,
   source/model revision state, required artifact inventory, package compatibility declaration,
   separate code and weight licenses, remote-code policy, pretraining disclosure, contamination
   risk, verification report, release state, and supersession state.
2. Unknown facts use explicit fail-closed values: `UNKNOWN`, `UNPINNED`, `UNVERIFIED`,
   `LICENSE_REVIEW_REQUIRED`, `REMOTE_CODE_REVIEW_REQUIRED`, or `NOT_RELEASED`.
3. Formal verified intake requires immutable revisions. `main`, `master`, `latest`, branch names,
   shortened hashes, and uppercase hashes are not formal pins.
4. Artifact paths are POSIX relative paths without traversal, absolute paths, backslashes, empty
   components, or duplicate paths.
5. The registry rejects duplicate source IDs, duplicate logical model IDs, invalid supersession
   references, and supersession cycles.
6. Canonical repositories must be official and must not be mirrors.
7. A remote-code record requires a concrete policy identifier and explicit review state.
8. A not-released model cannot be classified as available for intake.
9. Registry validation must always preserve runtime and production non-claims.

## Non-functional requirements

- Pydantic v2 models use `extra="forbid"`, `strict=True`, `allow_inf_nan=False`, and
  `validate_assignment=True`.
- No root dependency, lockfile, workflow, active catalog, provider, worker, runtime SDK,
  Data Access Ledger, raw data, Holdout, Prospective, Registry, or Promotion change is permitted.
- JSON parsing rejects duplicate keys and non-finite constants.
- Report writes are atomic within one filesystem directory.
- Canonical registry identity uses deterministic UTF-8 JSON and SHA-256.
- The package remains dependency-light and uses only the standard library and existing Pydantic v2.
