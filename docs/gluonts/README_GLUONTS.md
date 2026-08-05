# GluonTS isolated provider integration

Status: `PARTIALLY_VERIFIED`

This directory contains the version-isolated GluonTS integration. Real runtime success is not claimed
until target-machine evidence is available.

## Runtime lanes

| Lane | GluonTS | Torch |
|---|---:|---:|
| `compat` | 0.16.3 | 2.9.1 |
| `latest` | 0.17.0 | >=2.10,<3 |

The root Torch contract is unchanged. GluonTS objects never cross the JSON process boundary.

## Implemented phases

- **P1:** isolated dependency definitions and strict Pydantic request/response contracts.
- **P2:** provider CLIs, atomic JSON, retained logs, timeout and identity validation.
- **P3:** runtime inventory for Estimators, Predictors, extensions, and distributions.
- **P4:** bounded DeepAR CPU constructor, fit, predict, shape, finite, and device checks.
- **P5:** DeepAR Predictor serialization, process exit, new-process reload, and re-prediction.
- **P6:** independent lifecycle certification for all nine exported PyTorch Estimators.
- **P7:** cross-lane evidence validation and failure classification.
- **P7B:** exclusive, resumable target-machine supervision with source identity, per-stage timeout,
  signal-safe process groups, atomic stage journal, partial/final SHA inventories, and immutable resume.

## P6 models

```text
DeepNPTSEstimator
DeepAREstimator
TiDEEstimator
SimpleFeedForwardEstimator
TemporalFusionTransformerEstimator
WaveNetEstimator
DLinearEstimator
PatchTSTEstimator
LagTSTEstimator
```

Each model has an explicit constructor profile, distribution mode, minimum target length, and resource
limit. Unknown arguments, silent argument drops, larger-than-certified settings, artifact changes,
runtime-version drift, and same-process reload fail closed. The campaign uses at most eight outer
workers and one CPU thread per provider process.

## Preferred target-machine command

```bash
RUN_ID="gluonts-p7b-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/mnt/e/env/logs/${RUN_ID}"
RUN_ID="${RUN_ID}" bash environments/gluonts-p7b-target-machine.sh "${OUT}"
```

Resume an interrupted or incomplete run with the exact same output directory:

```bash
bash environments/gluonts-p7b-target-machine.sh "${OUT}" --resume
```

P7B refuses a dirty tracked worktree, a non-empty new output directory, concurrent ownership of the
same output, source/commit drift, or modified completed-stage evidence. Completed stages are not
repeated. Timed-out or interrupted attempts are moved under `history/` before retry.

Default stage limits are 14,400 seconds for each lane and 1,800 seconds for the audit. Override them
with `--compat-timeout-seconds`, `--latest-timeout-seconds`, and `--audit-timeout-seconds`.

The legacy non-resumable entry point remains available for compatibility:

```bash
bash environments/gluonts-p7-target-machine.sh
```

## P7B artifacts

```text
RUN_ID
p7b_preflight.json
p7b_execution_journal.json
p7b_execution_manifest.json
P7B_EXECUTION_COMPLETE
P7B_EXECUTION_SHA256SUMS
P7B_PARTIAL_SHA256SUMS
compat/
latest/
audit/
gpu_process_monitor.jsonl
history/
```

A lane process returning non-zero is still a completed execution stage. Its return code and artifacts
are passed to P7 for evidence-backed model classification; they are not replaced by a generic
supervisor failure.

See:

- `GLUONTS_P6_MODEL_MATRIX.md`
- `GLUONTS_P6_VERIFICATION_REPORT.md`
- `GLUONTS_P7_VERIFICATION_REPORT.md`
- `GLUONTS_P7B_VERIFICATION_REPORT.md`
- `GLUONTS_P7B_RUNBOOK.md`

## Current verification

```text
TOTAL_P6_FOCUSED_TESTS=21 passed
P7_AUDIT_TESTS=9 passed
P7B_CONTRACT_TESTS=6 passed
P7B_SUPERVISOR_TESTS=9 passed
TOTAL_P7B_FOCUSED_TESTS=15 passed
FAKE_TARGET_MACHINE_END_TO_END=PASS
NONZERO_LANE_RETURN_CODES_PRESERVED=PASS
FINALIZED_RESUME_WITHOUT_RERUN=PASS
COMPILEALL=PASS
P7B_BASH_SYNTAX=PASS
MAX_P7B_PYTHON_LINE_LENGTH=98
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

Chronological OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, and baseline comparisons remain a
later phase after all real model-lane lifecycles are formally verified.
