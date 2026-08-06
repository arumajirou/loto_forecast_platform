# AutoFreTS Runtime Certification Adapter

## Status

```text
PARTIALLY_VERIFIED
ADAPTER_AND_SOURCE_TESTS_PASS
REAL_NEURALFORECAST_RUNTIME_PENDING
DEPENDS_ON_PR_123_AND_PR_149
NOT_REGISTERED
ACCURACY_NOT_EVALUATED
```

## Purpose

This increment adds the provider-specific runtime adapter for the inactive local
`AutoFreTS` implementation introduced by Draft PR #149. It reuses the
provider-neutral Runtime Certification SDK from Draft PR #123.

It does not register the model, run OOF, open Holdout, open Prospective, or
claim forecasting accuracy.

## Dependency boundary

- PR #149 owns `FreTS(BaseModel)` and `AutoFreTS(BaseAuto)`.
- PR #123 owns common subprocess execution, output checks, replay, device
  evidence, manifests, SHA-256, and deterministic ZIP handling.
- PR #54 owns native Time-Series-Library FreTS provenance and CPU evidence.
- This change owns AutoFreTS-specific request/response contracts, source
  identity, isolated worker execution, SDK mapping, CLI, tests, and docs.

The common SDK is imported lazily. A checkout without PR #123 fails closed.

## Execution modes

```text
direct -> FreTS fixed configuration
ray    -> AutoFreTS with Ray and one fixed trial
optuna -> AutoFreTS with Optuna and one fixed trial
```

The Ray and Optuna modes prove backend lifecycle compatibility. They do not
compare search algorithms or establish HPO quality.

- no nested Ray;
- Ray requests one CPU and zero or one GPU for the single trial;
- Optuna uses `n_jobs=1`;
- seed defaults to 1;
- only deterministic synthetic input is used.

## FreTS-specific formal gates

Every PASS response must prove:

```text
fft_dtype=float32
precision=32-true
channel_frequency_mixing=false
temporal_fft_bins > 0
parameter_count == expected_parameter_count
```

The expected parameter formula is inherited from the reviewed foundation:

```text
66,432 + 32,768 * input_size + 257 * horizon
```

A GPU request still uses float32 FFT. Mixed precision is rejected rather than
silently changing FFT semantics.

## Runtime lifecycle

Each request launches two distinct provider processes. Every process must:

1. verify clean Git state and exact HEAD;
2. verify the exact ordered AutoFreTS source inventory;
3. verify `neuralforecast==3.2.0`;
4. construct deterministic float32 synthetic input;
5. construct the direct model or one-trial AutoModel;
6. fit;
7. produce exact `[1, horizon]` finite output;
8. save with `NeuralForecast.save()`;
9. reload with `NeuralForecast.load()`;
10. re-predict within tolerance;
11. re-open FreTS architecture metadata;
12. verify float32 parameters and exact parameter count;
13. verify requested/effective device equality;
14. reject CPU fallback;
15. collect GPU PID, UUID, VRAM, and `nvidia-smi` evidence for CUDA;
16. verify provider PID release after exit;
17. match the second process prediction within replay tolerance.

## Source identity

Certification hashes these exact paths:

```text
src/loto/neuralforecast/auto_frets/__init__.py
src/loto/neuralforecast/auto_frets/auto.py
src/loto/neuralforecast/auto_frets/contracts.py
src/loto/neuralforecast/auto_frets/model.py
src/loto/neuralforecast/auto_frets/runtime.py
src/loto/neuralforecast/auto_frets/runtime_contracts.py
src/loto/neuralforecast/auto_frets/runtime_source.py
src/loto/neuralforecast/auto_frets/runtime_worker.py
src/loto/neuralforecast/auto_frets/runtime_certification.py
src/loto/neuralforecast/auto_frets/certify.py
```

The canonical digest covers path, byte size, and per-file SHA-256. Symlinks,
path escape, missing files, dirty worktrees, detached HEADs, revision drift,
and byte drift are rejected.

## Fingerprint command

Run from the exact clean checkout intended for certification:

```bash
REVISION="$(git rev-parse HEAD)"
PYTHONDONTWRITEBYTECODE=1 \
uv run --frozen --extra full python -m \
  loto.neuralforecast.auto_frets.certify fingerprint \
  --working-directory "$PWD" \
  --source-revision "$REVISION"
```

Store redirected fingerprint output outside the repository because the source
gate requires a completely clean worktree.

## Request example

```json
{
  "schema_version": "1.0.0",
  "run_id": "auto-frets-cpu-direct-001",
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

CPU requests require `CPU_SMOKE` and `requested_device=cpu`. GPU requests
require `GPU_FORMAL` and `requested_device=cuda`. Precision is always
`32-true`.

## Operator command

The output directory must be new, absolute, and outside the Git worktree.

```bash
LOTO_NO_WAIT=1 \
bash scripts/run_auto_frets_runtime_certification.sh \
  --repo-root "$PWD" \
  --request /absolute/auto-frets-runtime-request.json \
  --output-root /absolute/artifacts/auto-frets-runtime/<run-id>
```

## Evidence output

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

Synthetic runtime input is not an accuracy dataset. Runtime certification does
not establish Hit@±1, MAE, MSE, RMSE, position Hit@±1, all-position Hit@±1,
baseline superiority, OOF validity, Holdout success, Prospective success,
champion status, or production eligibility.
