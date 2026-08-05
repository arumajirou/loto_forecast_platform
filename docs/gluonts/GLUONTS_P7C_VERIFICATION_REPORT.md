# GluonTS P7C result triage and remediation verification

Status: `PARTIALLY_VERIFIED`

## Objective

P7B produces immutable target-machine evidence. P7C reads that evidence without modifying it,
revalidates the complete P7B and P7 checksum inventories, and converts the 18 model-lane rows into an
evidence-backed remediation queue.

P7C does not silently fix code, install dependencies, rerun successful models, or promote a model
from discovery or constructor evidence. It only produces a plan and a strict P8 eligibility gate.

## Remediation classes

```text
VERIFIED
EVIDENCE_REPAIR
ENVIRONMENT_REPAIR
IMPLEMENTATION_REPAIR
TRANSIENT_RETRY
MANUAL_TRIAGE
```

Priorities are `P0` through `P4`. Invalid or incomplete evidence is P0. Environment and implementation
failures are P1. Timeouts and provider crashes are P2. Verified rows are retained as P4/no-action
rows so they remain visible and are not accidentally selected for diagnosis reruns.

## Input verification

P7C requires and verifies:

```text
P7B_EXECUTION_COMPLETE
P7B_EXECUTION_SHA256SUMS
p7b_execution_manifest.json
p7b_execution_journal.json
audit/P7_SHA256SUMS
audit/p7_target_machine_audit.json
audit/p7_failure_matrix.json
audit/p7_artifact_manifest.json
```

It rejects missing, additional, modified, duplicate, escaping, stale, cross-run, or hash-inconsistent
input. The P7C output directory must be outside the immutable P7B directory.

## P8 gate

`p8_eligible=true` only when all conditions hold:

```text
evidence_state == VALID
certification_status == VERIFIED
verified_model_lifecycles == 18
exactly 18 unique compat/latest model rows
all 18 rows are VERIFIED
no cross-lane evidence-repair item exists
```

## Outputs

```text
p7c_remediation_plan.json
p7c_remediation_queue.tsv
p7c_remediation_report.md
p7c_artifact_manifest.json
P7C_SHA256SUMS
```

The artifact manifest binds the P7B execution manifest, P7B checksum inventory, P7 audit, failure
matrix, P7C plan, TSV queue, and Markdown report by SHA-256.

## Verification

```text
P7C_FOCUSED_TESTS=15 passed
P7C_PUBLIC_API_TEST=added
COMPILEALL=PASS
P7C_BASH_SYNTAX=PASS
MAX_P7C_PYTHON_LINE_LENGTH=98
REAL_P7B_INPUT=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

Focused tests cover the P8 gate, duplicate rows, verified-row invariants, environment failures,
implementation failures, transient failures, unknown failures, invalid evidence, tampered input,
incorrect row count, audit/matrix count drift, output-location isolation, non-empty output refusal, and
SHA-256-complete output generation.

## Certification boundary

No real P7B target-machine artifact was available in the execution environment. Therefore P7C does
not claim a real GluonTS model success, real dependency failure, real model failure, GPU evidence, CPU
fallback, or P8 eligibility. Those states are derived only after the target-machine run is supplied.
