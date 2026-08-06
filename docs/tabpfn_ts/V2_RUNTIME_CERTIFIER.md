# TabPFN-TS V2 Runtime Certifier

Status: `IMPLEMENTED / MOCK_VERIFIED / REAL_RUNTIME_PENDING`

This stacked increment certifies the pinned legacy V2 checkpoint as an executable runtime. It does
not claim forecasting accuracy, TS-3 support, or production-champion eligibility.

## Certification boundary

A formal CUDA pass requires all of the following:

1. The snapshot directory equals revision
   `4972a65a1b30806315c6f92499959ffbfc69a673`.
2. `tabpfn-v2-regressor.ckpt` resolves inside the repository cache `blobs` directory.
3. SHA-256 equals
   `2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736`
   before pipeline construction.
4. The Prior Labs checkpoint license is explicitly accepted.
5. Hub access is offline and telemetry is disabled.
6. CUDA was requested and used without CPU fallback.
7. Model parameters expose a CUDA device.
8. The provider PID is observed by `nvidia-smi` with a GPU UUID and positive VRAM.
9. The provider PID disappears after process exit.
10. Two distinct provider processes produce 37 finite candidate scores with identical SHA-256
    under the same seed.

A CPU execution can only receive `CPU_SMOKE`; it is not a formal GPU runtime certification.

## Target-host command

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

uv run python scripts/certify_tabpfn_ts_v2_runtime.py \
  --repo-root "$PWD" \
  --provider-python "$PWD/environments/tabpfn-ts/.venv/bin/python" \
  --request /absolute/path/to/tabpfn-v2-certification-request.json \
  --snapshot /absolute/hf/cache/models--Prior-Labs--TabPFN-v2-reg/snapshots/4972a65a1b30806315c6f92499959ffbfc69a673 \
  --repository-cache-root /absolute/hf/cache/models--Prior-Labs--TabPFN-v2-reg \
  --device cuda \
  --seed 1 \
  --repeats 2 \
  --prediction-tolerance 0
```

The input request must contain the historical Loto7 rows. Identity, checkpoint, offline, seed,
license, and device fields are overwritten by the certifier with reviewed values.

## Artifacts

Each process stores its formal request, provider response, stdout, and stderr. The run root stores:

- `runtime-certification-report.json`
- `SHA256SUMS`
- `process-01/**`
- `process-02/**`

The report records the provider and external GPU evidence, process identity, response hash,
prediction hash, replay difference, and pre-actual prediction lock state.

## Failure policy

The certifier fails closed on missing or mismatched checkpoint provenance, license non-acceptance,
network-enabled execution, unavailable CUDA, CPU fallback, missing CUDA parameter evidence,
missing external PID/VRAM evidence, non-finite or incorrectly shaped output, unreleased GPU PID,
or non-reproducible separate-process predictions.

## Explicitly pending

- actual checkpoint load on the RTX 5070 Ti target host;
- real `nvidia-smi` PID/UUID/VRAM evidence;
- separate-process prediction replay using the real package environment;
- root Ruff, mypy, full pytest, and actionable GitHub Actions;
- OOF, Holdout, Prospective, Hit@±1, MAE, MSE, RMSE, and baseline comparisons.
