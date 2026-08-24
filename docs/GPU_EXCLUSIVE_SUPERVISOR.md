# GPU Exclusive Supervisor v1

`gpu_exclusive` is a deterministic CPU-side control plane for one-GPU systems where a local
LLM and a forecasting workload cannot coexist in VRAM.

It deliberately does **not** contain an LLM router. One run executes this fixed sequence:

1. optionally quiesce an already-running external request gate and wait for exact `in_flight=0`;
2. close that gate;
3. unload the configured Qwen/LLM runtime through its existing HTTP control API;
4. verify with `nvidia-smi` that GPU memory remains below the configured free threshold for
   multiple consecutive samples;
5. run exactly one forecast command with `CUDA_VISIBLE_DEVICES` pinned to the configured GPU;
6. continuously check that Qwen does not reappear while the forecast owns the GPU;
7. wait for the GPU to become free again;
8. restore Qwen if it was running before the handoff;
9. reopen the external gate only after Qwen health is restored.

A failure after Qwen has been unloaded still attempts Qwen restoration. If restoration fails,
the request gate remains closed (fail closed).

## Why this exists

The supervisor separates the control plane from the LLM that is being unloaded. A local Qwen
session must not be responsible for continuing the handoff after it has unloaded itself.

The module also detects the observed failure mode where a GUI/browser bypasses the request gate
and causes llama-swap to lazily reload Qwen during the forecast window. When Qwen reappears, the
forecast process is terminated and the run is marked failed.

## Configuration

Create a JSON file matching `loto.gpu_exclusive.models.SupervisorConfig`. Use the exact URLs and
model alias from the local environment; do not guess them.

```json
{
  "qwen": {
    "running_url": "http://127.0.0.1:18081/running",
    "running_contains": "<MODEL_ALIAS>",
    "start_url": "http://127.0.0.1:18081/upstream/<MODEL_ALIAS>/",
    "start_method": "GET",
    "stop_url": "http://127.0.0.1:18081/api/models/unload/<MODEL_ALIAS>",
    "stop_method": "POST"
  },
  "gate": {
    "status_url": "http://127.0.0.1:18083/control/status",
    "quiesce_url": "http://127.0.0.1:18083/control/quiesce",
    "close_url": "http://127.0.0.1:18083/control/close",
    "open_url": "http://127.0.0.1:18083/control/open",
    "in_flight_field": "in_flight"
  },
  "gpu": {
    "index": 0,
    "max_memory_used_mib_when_free": 1024,
    "stable_samples": 3
  },
  "forecast": {
    "command": ["uv", "run", "python", "/absolute/path/to/forecast_smoke.py"],
    "cwd": "/mnt/e/env/ts/loto_forecast_platform",
    "env": {},
    "timeout_seconds": 1800
  },
  "output_dir": "/mnt/e/env/ts/loto_gpu_runs/gpu-exclusive-smoke"
}
```

For llama-swap v250, model unload is an explicit POST control operation while
model startup is lazy and is triggered by a GET request to `/upstream/<MODEL_ALIAS>/`.
`start_method` and `stop_method` default to `POST` so existing HTTP-controlled
runtimes remain backward compatible.

Run it with:

```bash
uv run loto-gpu-exclusive --config /absolute/path/to/gpu-exclusive.json
```

## Acceptance order

Do not begin with a long forecasting campaign. Certify in this order:

1. Qwen unload -> stable GPU-free -> Qwen restore -> real Qwen response;
2. Qwen already off -> one short forecasting CUDA smoke -> GPU-free;
3. full unload -> one forecast -> restore E2E;
4. repeat the E2E multiple times before connecting Hermes/DSH/OpenCode to it.

The control plane is Linux-first because the current local GPU stack is Linux/NVIDIA and process
group cleanup uses POSIX semantics when available. The Python interfaces themselves avoid shell
strings and execute command arguments directly.
