# GluonTS P6B all-nine Estimator lifecycle verification

Status: `PARTIALLY_VERIFIED`

P6A provides constructor-only evidence and the broader explicit distribution matrix. P6B adds
bounded fit, predict, serialize, process restart, deserialize, and re-predict evidence for one
upstream-tested combination per model.

P6B uses eight outer workers, one CPU thread per provider, one epoch, one batch per epoch, batch size
four, prediction length one, and seed one. DeepAR and TFT use StudentTOutput. The other seven models
use the default output behavior exercised by upstream `test/torch/model/test_estimators.py`.

```text
P6B_REGISTRY_TESTS=4 passed
P6B_CONTRACT_TESTS=3 passed
P6B_FAKE_RUNTIME_TESTS=12 passed
P6B_CAMPAIGN_TESTS=2 passed
TOTAL_P6B_FOCUSED_TESTS=21 passed
COMPILEALL=PASS
COMPAT_BOOTSTRAP_BASH_SYNTAX=PASS
LATEST_BOOTSTRAP_BASH_SYNTAX=PASS
REAL_GLUONTS_RUNTIME=EXECUTION_PENDING
FORMALLY_VERIFIED_MODEL_LIFECYCLES=0
```

Each stage independently checks registry, runtime version, import, constructor signature, bounded
resources, constructor, dataset, fit, prediction shape, finite values, observed CPU device,
serialization, artifact tree integrity, distinct process PID, deserialization, and identity. Every
non-verified stage records a failure category.

Implementation defects found and fixed include nested override expansion, incomplete reload identity,
self-referential SHA sums, provenance loss after non-zero campaign exit, campaign crash evidence loss,
effective-context omission, test PID patching at the wrong module, unused imports, and a distribution
matrix initially inconsistent with the upstream lifecycle fixture.

No real runtime success, accuracy improvement, GPU PID/VRAM, CUDA, CPU fallback, OOF, Holdout, or
Prospective result is claimed. P7 must execute both isolated lane bootstraps on the target machine and
retain all per-model failures, lockfiles, logs, artifacts, provenance, and SHA-256 manifests.
