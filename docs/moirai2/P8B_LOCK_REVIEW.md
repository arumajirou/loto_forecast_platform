# P8B Isolated Lock Review

## Goal

P8B closes the gap between an unreviewed `uv.lock` and the P8A frozen-runtime preflight. It does not
resolve or approve a lock inside CI and does not execute the model.

## Evidence flow

```text
lane pyproject.toml
        |
        v
new immutable candidate directory
        |
        +-- candidate-project/pyproject.toml
        +-- candidate-project/uv.lock
        +-- LOCK_DEPENDENCY_INVENTORY.csv
        +-- LOCK_REVIEW_REPORT.json
        +-- CANDIDATE_RESULT.json
        +-- SHA256SUMS
        |
        v
human review
        |
        +-- reviewer identity
        +-- timezone-aware reviewed_at
        +-- expected candidate lock SHA-256
        +-- explicit approval token
        |
        v
atomic lane installation
        |
        +-- uv.lock
        +-- LOCK_REVIEW_REPORT.json
        +-- LOCK_REVIEW_APPROVAL.json
        |
        v
P8A preflight cross-hash validation
```

## Automated review policy

The lock review requires:

- all direct dependencies to be single exact pins;
- every direct pin to be represented in the lock;
- only registry sources for external packages;
- one root virtual package at `.` when emitted by uv;
- at least one valid SHA-256 artifact hash for every registry package;
- all dependency names to resolve to locked package entries;
- deterministic package, source, edge, and hash inventory.

The following fail closed:

- Git/VCS sources;
- path, directory, workspace, or editable sources;
- direct URLs in project dependencies;
- environment markers in direct project dependencies;
- missing package names or versions;
- missing or malformed registry artifact hashes;
- unresolved dependency edges;
- changed project, lock, report, approval, or runtime lane identity.

Multiple locked versions are retained as a warning and require human inspection. They are not silently
collapsed.

## Installation policy

The installer writes evidence to a separate new output directory and never modifies the candidate
artifact. It defaults to dry-run. `--apply` additionally requires the exact token
`APPLY-REVIEWED-MOIRAI2-LOCK`. Existing reviewed-lock artifacts are never replaced without the
currently installed lock SHA-256. A replacement is backed up before atomic writes.

## Certification boundary

P8B automated checks cannot decide whether a dependency is desirable, safe for the user's machine,
legally acceptable beyond the existing project policy, or compatible with the target GPU. Those
remain human and target-host gates. P8B does not claim real dependency resolution, import, inference,
accuracy, or production eligibility.
