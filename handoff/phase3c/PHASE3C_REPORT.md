# Phase 3C Runtime Gap Review

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- unresolved environments reviewed: 10
- ambiguous environments reviewed: 2
- sys.prefix runtime identities considered: 20

## Classification

- `BROKEN_DECLARED_RUNTIME`: 4
- `CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE`: 7
- `REUSABLE_COMPATIBLE_VENV`: 1

## Interpretation

`BROKEN_DECLARED_RUNTIME` means the declared project venv has broken Python symlink evidence.

`REUSABLE_COMPATIBLE_VENV` means an existing venv matches the declared Python constraint and direct dependencies at the metadata level. It is not yet formal model certification.

`CANDIDATE_REQUIRES_SEPARATE_FORMAL_LANE` means a related existing venv exists but does not fully satisfy the declared dependency contract, so it must not silently replace the formal lane.

`NO_RUNTIME_FOUND` means no sufficiently related existing venv was found from current runtime identities.

No dependency was installed or modified. No model checkpoint was loaded.
