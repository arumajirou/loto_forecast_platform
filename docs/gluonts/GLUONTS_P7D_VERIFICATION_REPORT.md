# GluonTS P7D evidence handoff verification

Status: `PARTIALLY_VERIFIED`

## Objective

P7D creates a portable, self-verifying ZIP from a completed P7C orchestration root. It preserves the
P7B execution tree, P7 audit, P7C remediation plan, logs, return codes, and all nested checksum files.
The bundle records the exact run ID, Git commit, evidence state, certification state, verified
model-lane count, P8 state, file sizes, and SHA-256 values.

## Bundle layout

```text
P7D_BUNDLE_MANIFEST.json
P7D_SHA256SUMS
P7D_BUNDLE_COMPLETE
run/**
```

A sibling `<archive>.sha256` records the final ZIP SHA-256. ZIP members use sorted names, fixed member
timestamps, regular-file permissions, ZIP64, and DEFLATE level 6.

## Verification layers

1. Validate ZIP member names, uniqueness, type, compression, and expansion limits.
2. Verify `P7D_SHA256SUMS` and every manifest entry size/hash.
3. Safely extract to a temporary directory.
4. Revalidate `P7C_ORCHESTRATION_SHA256SUMS`.
5. Revalidate nested P7B, P7, and P7C checksum inventories.
6. Reconcile run ID, commit SHA, audit hash, failure-matrix hash, return codes, and P8 state.
7. Optionally place the verified tree atomically and write a new verification inventory.

## Focused verification

```text
P7D_FOCUSED_AND_PUBLIC_API_TESTS=13 passed
COMPILEALL=PASS
P7D_BASH_SYNTAX=PASS
MAX_P7D_PYTHON_LINE_LENGTH=86
REAL_TARGET_MACHINE_BUNDLE=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

Tests cover normal and P8-eligible round trips, source tampering, ZIP tampering, duplicate members,
path traversal, symlink members, output isolation, existing archive refusal, non-empty extraction
refusal, sidecar creation, and complete verification-output hashing.

## Certification boundary

No real target-machine P7C orchestration directory was available. P7D therefore does not claim a real
model lifecycle result, real remediation count, GPU observation, CPU fallback, or P8 eligibility. It
only certifies the handoff implementation against synthetic immutable evidence.
