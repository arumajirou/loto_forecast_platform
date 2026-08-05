# GluonTS P6 all-nine Estimator lifecycle verification

## Status

```text
PHASE=GLUONTS_P6
STATUS=PARTIALLY_VERIFIED
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LIFECYCLES=0
```

## Implemented

P6 adds an independent, version-isolated lifecycle for all nine PyTorch
Estimators exported by GluonTS 0.16.3 and 0.17.0:

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

The official 0.16.3 and 0.17.0 `gluonts.torch` export lists are identical.
A tag-to-tag source comparison did not identify changes to the nine Estimator
implementation files used by this registry. P6 nevertheless validates the
actual runtime signature before every constructor call.

## Fail-closed classification

Every non-verified stage records one category, including:

```text
VERSION_MISMATCH
MODEL_UNSUPPORTED
DISTRIBUTION_UNSUPPORTED
SIGNATURE_MISMATCH
UNSUPPORTED_ARGUMENT
RESOURCE_POLICY_VIOLATION
IMPORT_FAILED
CONSTRUCTOR_FAILED
DATASET_FAILED
FIT_FAILED
PREDICT_FAILED
OUTPUT_SHAPE_FAILED
NON_FINITE_OUTPUT
DEVICE_MISMATCH
SERIALIZE_FAILED
ARTIFACT_INTEGRITY_FAILED
PROCESS_RESTART_REQUIRED
DESERIALIZE_FAILED
IDENTITY_MISMATCH
UNKNOWN
```

## Artifact identity

Each serialized Predictor directory includes:

```text
p6_certification_dataset.json
p6_constructor_arguments.json
p6_predictor_manifest.json
<native GluonTS Predictor files>
```

The manifest binds the lane, model, distribution, fit PID, seed, frequency,
horizon, effective context, registry SHA, model-spec SHA, constructor-document
SHA, dataset SHA, pre-reload prediction SHA, runtime versions, every file
path/size/SHA, and the deterministic artifact-tree SHA.

The reload process rejects missing, additional, renamed, modified, duplicated,
absolute, or parent-traversal paths before deserialization. It also rejects a
changed lane, model, distribution, horizon, frequency, context, registry,
model specification, runtime version, or unchanged process ID.

## Campaign execution

The root campaign uses up to eight outer workers. One model failure does not
abort evidence collection for the other models. A failed future or provider
crash is converted into a model-specific `UNKNOWN` failure lifecycle.

Campaign artifacts:

```text
p6_campaign_result.json
p6_campaign_manifest.json
p6_environment_provenance.json
P6_SHA256SUMS
provider/<model>/<stage>/request.json
provider/<model>/<stage>/response.json
provider/<model>/<stage>/stdout.log
provider/<model>/<stage>/stderr.log
predictors/<model>/...
```

## Focused verification

```text
registry_tests=4 passed
contract_tests=3 passed
fake_runtime_tests=12 passed
campaign_tests=2 passed
total_p6_focused_tests=21 passed
compileall=PASS
compat_bootstrap_bash_syntax=PASS
latest_bootstrap_bash_syntax=PASS
maximum_changed_python_line_length=100
```

The fake runtime covers all nine fit, serialize, different-PID reload, and
re-predict paths. It also covers unknown constructor arguments, signature
mismatch, missing runtime versions, and campaign short-circuit behavior.

## Defects found and fixed

1. Root and provider copies of the same `StrEnum` were imported into one test
   process; identity comparison was therefore false despite equal values. The
   test now resolves the isolated provider source explicitly.
2. `P6_SHA256SUMS` initially included itself, creating a self-referential hash.
3. Bootstrap initially exited before provenance when the campaign was nonzero.
4. One model crash initially aborted aggregate campaign evidence.
5. Nested trainer overrides initially permitted new keys or larger capacities.
6. Reload identity initially omitted distribution, horizon, frequency, and
   effective context checks.
7. The manifest now stores the effective context rather than only an explicit
   request override.
8. The initial monolithic runtime was split into common, fit, reload, and facade
   modules; all focused tests continued to pass.

## Certification boundary

The execution registry available during implementation did not provide the
pinned GluonTS lane packages. Therefore this phase does not claim:

- successful `uv lock` or package installation on the target machine,
- real constructor, fit, predict, serialize, or cross-process deserialize,
- real output shape, finite-value, or observed-device evidence,
- GPU PID, VRAM, CUDA, or CPU fallback evidence,
- chronological OOF, Holdout, Prospective, or accuracy improvement.

The formal lifecycle count remains zero until a target-machine bootstrap
produces `VERIFIED` evidence for each model.

## Next phase

P7 should run the two P6 bootstraps on the target machine, classify real
per-model failures, correct only evidence-backed incompatibilities, and retain
all lockfiles, environment provenance, model artifacts, logs, and SHA-256
manifests. Accuracy evaluation remains a later, separate chronological phase.
