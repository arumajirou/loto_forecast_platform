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
- **P7:** cross-lane target-machine execution, provenance validation, failure classification, and immutable evidence audit.

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
limit. The provider checks the actual runtime constructor signature before instantiation. Unknown
arguments, silent argument drops, larger-than-certified settings, artifact changes, runtime-version
drift, and same-process reload fail closed.

The campaign uses at most eight outer workers and one CPU thread per provider job. Reload starts only
after that model's fit/serialize stage is verified. One model failure does not discard evidence from
the other models. The campaign is `VERIFIED` only when all nine independent lifecycles pass.

See:

- `GLUONTS_P6_MODEL_MATRIX.md`
- `GLUONTS_P6_VERIFICATION_REPORT.md`

## P6 artifacts

```text
predictors/<model>/p6_certification_dataset.json
predictors/<model>/p6_constructor_arguments.json
predictors/<model>/p6_predictor_manifest.json
provider/<model>/<stage>/request.json
provider/<model>/<stage>/response.json
provider/<model>/<stage>/stdout.log
provider/<model>/<stage>/stderr.log
p6_campaign_result.json
p6_campaign_manifest.json
p6_environment_provenance.json
P6_SHA256SUMS
```

## P7 target-machine execution

Run both isolated lanes and the cross-lane evidence auditor with one command:

```bash
bash environments/gluonts-p7-target-machine.sh
```

The compatibility and latest lanes run sequentially. Each lane retains the P6 eight-worker campaign.
The runner records both return codes, stdout, stderr, isolated environment provenance, all model and
Predictor artifacts, and a two-second GPU PID/VRAM process monitor.

P7 distinguishes evidence validity from model certification:

```text
Evidence:      VALID | INCOMPLETE | INVALID
Certification: VERIFIED | PARTIALLY_VERIFIED | BLOCKED | FAILED | NOT_EVALUATED
```

A real model failure with correct hashes remains valid evidence and is written to
`p7_failure_matrix.json`. Tampered, missing, additional, or provenance-inconsistent artifacts never
become model failures; they are rejected as invalid or incomplete evidence.

P7 outputs:

```text
p7_target_machine_audit.json
p7_failure_matrix.json
p7_artifact_manifest.json
P7_SHA256SUMS
gpu_process_monitor.log
P7_EXECUTION_SHA256SUMS
```

See `GLUONTS_P7_VERIFICATION_REPORT.md` for the complete contract and exit codes.

## Individual lane commands

```bash
bash environments/gluonts-compat/p6_bootstrap_and_certify.sh
bash environments/gluonts-latest/p6_bootstrap_and_certify.sh
```

Each command performs isolated `uv lock`, `uv sync --frozen`, the eight-worker campaign, provenance
generation, and complete artifact hashing. Failure evidence is written before a non-zero exit. P6
provenance is generated through the lane's `uv run` interpreter, not the system Python.

## Current verification

```text
P6_REGISTRY_TESTS=4 passed
P6_CONTRACT_TESTS=3 passed
P6_FAKE_RUNTIME_TESTS=12 passed
P6_CAMPAIGN_TESTS=2 passed
TOTAL_P6_FOCUSED_TESTS=21 passed
P7_AUDIT_TESTS=9 passed
COMPILEALL=PASS
BOOTSTRAP_BASH_SYNTAX=PASS
P7_TARGET_RUNNER_BASH_SYNTAX=PASS
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LANE_LIFECYCLES=0
```

Chronological OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, and baseline comparisons remain a
later phase after all real model-lane lifecycles are formally verified.
