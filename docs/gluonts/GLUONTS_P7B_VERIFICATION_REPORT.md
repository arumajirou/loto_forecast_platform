# GluonTS P7B target-machine supervision verification

Status: `PARTIALLY_VERIFIED`

## Objective

P7 validates completed P6 lane evidence. P7B adds the missing operational layer required to produce
that evidence safely on the target machine. It does not alter the P6 model contract or the P7 audit
classification rules.

The P7B supervisor provides:

- exclusive output-directory locking,
- refusal to overwrite a non-empty run directory,
- clean tracked-worktree and Git commit identity capture,
- SHA-256 identity for the runner, P6/P7 contracts, registries, and lane bootstrap scripts,
- configurable timeouts for compatibility, latest, and audit stages,
- process-group termination on timeout or signal,
- atomic execution journal updates,
- resumable execution without repeating completed stages,
- preservation and archiving of interrupted attempts,
- tamper detection before resume,
- two-second GPU process, PID, process-name, and VRAM JSONL monitoring,
- final execution manifest and complete SHA-256 inventory.

A lane command returning non-zero is still a completed execution stage. Its artifacts are retained and
passed to the P7 auditor. This prevents real model failures from being confused with supervisor or
evidence failures.

## Stage model

```text
preflight
compat_bootstrap
latest_bootstrap
audit
finalize
```

Stage states are:

```text
PENDING
RUNNING
COMPLETED
TIMED_OUT
INTERRUPTED
FAILED_TO_START
SKIPPED
```

`COMPLETED` means that the process exited and its output identity was recorded. It does not imply a
zero return code or a verified model result.

## Resume contract

A resume is accepted only when:

- the same output directory contains a P7B journal,
- the repository branch, commit, tracked-worktree state, and source SHA-256 identities are unchanged,
- every previously completed stage still has the same stdout, stderr, return-code, and artifact
  identity,
- any partial SHA-256 inventory verifies before it is archived,
- the execution has not already been finalized with a valid complete checksum inventory.

Completed compatibility, latest, and audit stages are never repeated. Interrupted, timed-out, or
failed-to-start attempts are archived under `history/` before a new attempt begins.

## Artifacts

```text
RUN_ID
p7b_preflight.json
p7b_execution_journal.json
p7b_execution_manifest.json
P7B_EXECUTION_COMPLETE
P7B_EXECUTION_SHA256SUMS
P7B_PARTIAL_SHA256SUMS              # incomplete/interrupted runs only
gpu_process_monitor.jsonl
compat/
latest/
audit/
compat_bootstrap.stdout.log
compat_bootstrap.stderr.log
compat_bootstrap.rc
latest_bootstrap.stdout.log
latest_bootstrap.stderr.log
latest_bootstrap.rc
audit.stdout.log
audit.stderr.log
audit.rc
history/
```

The lock file is excluded from checksum inventories because its PID changes when a finalized run is
opened for verification.

## Local verification

```text
P7B_CONTRACT_TESTS=6 passed
P7B_SUPERVISOR_TESTS=9 passed
TOTAL_P7B_FOCUSED_TESTS=15 passed
PY_COMPILE=PASS
BASH_SYNTAX=PASS
MAX_P7B_PYTHON_LINE_LENGTH=98
FAKE_TARGET_MACHINE_END_TO_END=PASS
NONZERO_LANE_RETURN_CODES_PRESERVED=PASS
FINALIZED_RESUME_WITHOUT_RERUN=PASS
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

The end-to-end fixture ran both lane scripts with non-zero return codes, completed the audit, generated
and validated the final journal and manifest, fixed all execution files in
`P7B_EXECUTION_SHA256SUMS`, and returned the same audit code on a finalized `--resume` without
re-running either lane.

## Certification boundary

P7B proves the supervision, resume, timeout, locking, and artifact-integrity behavior using fake lane
commands. It does not claim successful installation or execution of GluonTS 0.16.3 or 0.17.0, real
Predictor serialization, real CPU parameter-device evidence, GPU use, CPU fallback, accuracy, OOF,
Holdout, or Prospective results.
