# Runbook

## 1. Generate a lock candidate

Run on the target host from the repository root:

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
bash environments/toto2-4m-py312/bootstrap-lock-candidate.sh
```

Review the generated `uv.lock`, dependency tree, frozen requirements, package sources, hashes,
and licenses. Do not commit or approve the lock solely because resolution succeeded.

## 2. Prepare an exact request

The request must use schema v2, a formal context length of 128, 256, or 512, horizon 1, 2, or 5,
and decode block size divisible by 32. It must set `local_files_only=true` and may include the exact
snapshot path.

## 3. Run two-process runtime certification

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
RUN_ID="toto2-4m-$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$PWD/artifacts/toto2-4m-runtime/$RUN_ID"
SNAPSHOT="/mnt/e/env/huggingface/hub/models--Datadog--Toto-2.0-4m/snapshots/8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9"

python scripts/certify_toto2_4m_runtime.py \
  --request /absolute/path/predict-request.json \
  --response "$RUN_DIR/provider-response.json" \
  --snapshot "$SNAPSHOT" \
  --isolated-python "$PWD/environments/toto2-4m-py312/.venv/bin/python" \
  --run-dir "$RUN_DIR"
```

The command must fail unless both child processes pass snapshot, dependency, model identity,
shape, finite-value, quantile monotonicity, device, and exact replay checks. CUDA requests also
require an external `nvidia-smi` observation of each provider PID.

## 4. Dependency-light validation only

Existing native output may be validated without loading Toto:

```bash
python scripts/run_toto2_4m_provider.py \
  --request /absolute/path/predict-request.json \
  --native-output /absolute/path/native-output.npy \
  --runtime-evidence /absolute/path/runtime-evidence.json \
  --artifact-reference /absolute/path/artifact-reference.json \
  --response /absolute/path/response.json
```

A predict request without runtime evidence reports `BLOCKED`; it is not inference success.
