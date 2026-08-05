# GluonTS isolated provider integration

Status: `PARTIALLY_VERIFIED`

This directory contains the version-isolated GluonTS integration. Real runtime success is not claimed
until immutable target-machine evidence is available.

## Runtime lanes

| Lane | GluonTS | Torch |
|---|---:|---:|
| `compat` | 0.16.3 | 2.9.1 |
| `latest` | 0.17.0 | >=2.10,<3 |

The root Torch contract is unchanged. GluonTS objects never cross the JSON process boundary.

## Implemented phases

- **P1:** isolated dependencies and strict Pydantic process contracts.
- **P2:** provider CLIs, atomic JSON, logs, timeout, and identity validation.
- **P3:** runtime inventory for Estimators, Predictors, extensions, and distributions.
- **P4:** bounded DeepAR CPU fit/predict certification.
- **P5:** Predictor serialization, process exit, reload, and re-prediction.
- **P6:** independent lifecycle certification for all nine PyTorch Estimators.
- **P7:** cross-lane evidence audit and failure classification.
- **P7B:** resumable target-machine supervision and immutable execution evidence.
- **P7C:** read-only result triage, remediation queue generation, and the P8 gate.

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

Each lane uses at most eight outer workers and one CPU thread per provider job. A model is verified only
when fit, prediction shape, finite values, observed device, native serialization, process restart,
deserialization, re-prediction, artifact identity, and distinct PIDs all pass.

## P7B target-machine execution

```bash
RUN_ID="gluonts-p7b-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/mnt/e/env/logs/${RUN_ID}"
RUN_ID="${RUN_ID}" bash environments/gluonts-p7b-target-machine.sh "${OUT}"
```

Resume with:

```bash
bash environments/gluonts-p7b-target-machine.sh "${OUT}" --resume
```

P7B records the exact Git commit, tracked-worktree state, source hashes, stage commands, return codes,
stdout, stderr, timeouts, process groups, GPU PID/process/VRAM samples, stage identities, and a complete
SHA-256 inventory.

## P7C execution and triage

Run P7B and P7C together:

```bash
RUN_ID="gluonts-p7c-$(date -u +%Y%m%dT%H%M%SZ)"
OUT="/mnt/e/env/logs/${RUN_ID}"
RUN_ID="${RUN_ID}" bash environments/gluonts-p7c-target-machine.sh "${OUT}"
```

Analyze an existing completed P7B run without modifying it:

```bash
bash environments/gluonts-p7c-analyze.sh \
  "${P7B_OUT}" \
  "${P7B_OUT}-p7c"
```

P7C classifies each model-lane row as:

```text
VERIFIED
EVIDENCE_REPAIR
ENVIRONMENT_REPAIR
IMPLEMENTATION_REPAIR
TRANSIENT_RETRY
MANUAL_TRIAGE
```

The P7C output must be outside the immutable P7B directory. P7C writes a JSON plan, TSV queue,
Markdown report, artifact manifest, and complete checksum inventory.

## P8 gate

P8 remains blocked unless P7C reports all of the following:

```text
evidence_state=VALID
certification_status=VERIFIED
verified_model_lifecycles=18
p8_eligible=true
```

## Current verification

```text
P6_FOCUSED_TESTS=21 passed
P7_AUDIT_TESTS=9 passed
P7B_FOCUSED_TESTS=15 passed
P7C_FOCUSED_TESTS=16 passed
COMPILEALL=PASS
P7B_AND_P7C_BASH_SYNTAX=PASS
MAX_P7C_PYTHON_LINE_LENGTH=98
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

Chronological OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, and baseline comparisons begin only
after the strict P8 gate is satisfied.
