# AutoSegRNN Runtime Certification Adapter

## Status

```text
PARTIALLY_VERIFIED
ADAPTER_AND_CONTRACT_TESTS_PASS
REAL_NEURALFORECAST_RUNTIME_PENDING
DEPENDS_ON_PR_123_AND_PR_136
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Purpose

This increment adds the provider-specific runtime adapter for the inactive local
`AutoSegRNN` implementation introduced by Draft PR #136. It reuses the
provider-neutral Runtime Certification SDK from Draft PR #123.

It does not register the model, run OOF, open Holdout, open Prospective, or
claim forecasting accuracy.

## Dependency boundary

- PR #136 owns the local `SegRNN(BaseModel)` and `AutoSegRNN(BaseAuto)` classes.
- PR #123 owns common subprocess execution, identity verification, output checks,
  replay verification, device evidence, manifests, SHA-256, and deterministic ZIP.
- This change owns only AutoSegRNN-specific request/response contracts, source
  identity, worker execution, SDK mapping, operator CLI, tests, and documentation.

The common SDK is imported lazily. A checkout without PR #123 fails closed.

## Execution modes

One runtime request selects exactly one mode:

```text
direct   -> SegRNN fixed configuration
ray      -> AutoSegRNN with Ray backend and one fixed trial
optuna   -> AutoSegRNN with Optuna backend and one fixed trial
```

Ray and Optuna modes prove that the respective backend can construct, fit, select,
predict, save, load, and re-predict the local model. They do not compare search
algorithms and do not claim HPO quality.

Nested Ray is not used. Ray reserves one CPU and either zero or one GPU per trial.
Optuna uses `n_jobs=1` inside each isolated provider process.

## Runtime lifecycle

Each request launches two distinct provider processes. Every process must complete:

1. clean Git and exact HEAD verification;
2. exact source-tree SHA-256 verification;
3. exact `neuralforecast==3.2.0` verification;
4. deterministic synthetic input construction;
5. model or AutoModel construction;
6. fit;
7. prediction with exact `[1, horizon]` finite output;
8. `NeuralForecast.save()`;
9. `NeuralForecast.load()`;
10. re-prediction within the configured tolerance;
11. requested/effective device equality;
12. GPU PID, UUID, positive VRAM, and external `nvidia-smi` evidence for CUDA;
13. post-exit provider PID release verification;
14. cross-process prediction replay verification.

## Source identity

Certification requires a clean, non-detached Git checkout whose `HEAD` equals the
request `source_revision`.

The adapter hashes the exact ordered source inventory:

```text
src/loto/neuralforecast/auto_segrnn/__init__.py
src/loto/neuralforecast/auto_segrnn/auto.py
src/loto/neuralforecast/auto_segrnn/contracts.py
src/loto/neuralforecast/auto_segrnn/model.py
src/loto/neuralforecast/auto_segrnn/runtime.py
src/loto/neuralforecast/auto_segrnn/runtime_contracts.py
src/loto/neuralforecast/auto_segrnn/runtime_source.py
src/loto/neuralforecast/auto_segrnn/runtime_worker.py
src/loto/neuralforecast/auto_segrnn/runtime_certification.py
src/loto/neuralforecast/auto_segrnn/certify.py
```

The canonical digest covers each relative path, byte size, and file SHA-256. The
same digest is verified by the parent process and each provider process.

A byte-exact source snapshot is copied into the evidence directory under a directory
named with the 40-character Git revision. The common SDK independently reopens and
verifies that snapshot before runtime certification.

## Source fingerprint command

Run from a clean checkout at the exact intended commit:

```bash
REVISION="$(git rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 \
uv run --frozen --extra full python -m \
  loto.neuralforecast.auto_segrnn.certify fingerprint \
  --working-directory "$PWD" \
  --source-revision "$REVISION"
```

Review the returned revision, combined digest, paths, sizes, and per-file hashes.
Use the returned `source_tree_sha256` in the runtime request. If stdout is redirected
to a file, place that file outside the Git worktree because the fingerprint gate requires
a completely clean checkout.

## Request outline

```json
{
  "schema_version": "1.0.0",
  "run_id": "auto-segrnn-cpu-direct-001",
  "profile": "CPU_SMOKE",
  "execution_mode": "direct",
  "requested_device": "cpu",
  "expected_neuralforecast_version": "3.2.0",
  "source_revision": "<40 lowercase hex>",
  "source_tree_sha256": "<64 lowercase hex>",
  "horizon": 1,
  "architecture_profile": "compact",
  "training_profile": "smoke",
  "learning_rate": 0.001,
  "batch_size": 4,
  "windows_batch_size": 8,
  "dropout": 0.1,
  "scaler_type": "identity",
  "seed": 1,
  "history_length": 96,
  "validation_size": 1,
  "precision": "32-true",
  "replay_tolerance": 0.0,
  "timeout_seconds": 3600.0,
  "working_directory": "/absolute/clean/repository"
}
```

CPU requests require `CPU_SMOKE`, `requested_device=cpu`, and `precision=32-true`.
GPU requests require `GPU_FORMAL` and `requested_device=cuda`.

## Operator command

The output directory must be absolute, new, and outside the Git worktree.

```bash
LOTO_NO_WAIT=1 \
bash scripts/run_auto_segrnn_runtime_certification.sh \
  --repo-root "$PWD" \
  --request /absolute/auto-segrnn-runtime-request.json \
  --output-root /absolute/artifacts/auto-segrnn-runtime/<run-id>
```

Omit `LOTO_NO_WAIT=1` to retain the operator preference to wait for Enter.

## Evidence output

A successful or blocked attempt retains, as applicable:

```text
RUNTIME_REQUEST.json
source_snapshot/<source_revision>/**
processes/run-a/**
processes/run-b/**
CERTIFICATION_REPORT.json or CERTIFICATION_FAILURE.json
SHA256SUMS
<run-directory>.zip
<run-directory>.zip.sha256
```

## Accuracy boundary

Synthetic runtime input is not an accuracy dataset. Runtime certification does not
establish Hit@±1, MAE, MSE, RMSE, position-level Hit@±1, all-position Hit@±1,
baseline superiority, OOF validity, Holdout success, Prospective success, champion
status, or production eligibility.
