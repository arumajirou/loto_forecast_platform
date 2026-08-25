# Adaptive GPU Residency

## Status

`SOURCE_IMPLEMENTATION=EXECUTED_ON_TAJ_77_BRANCH`

`TARGET_MACHINE_CERTIFICATION=EXECUTION_PENDING`

This feature extends the existing deterministic GPU HANDOFF path. It does **not**
replace `ExclusiveGpuSupervisor`; HANDOFF remains the compatibility fallback and
the default policy. Target-machine COEXIST is not certified by source code or CI.

## Goal

Allow Forecast MCP to choose one of these operator-controlled modes:

| Mode | Meaning |
|---|---|
| `auto` | Select `coexist` only with exact certified evidence; otherwise fall back to `handoff` |
| `coexist` | Keep the selected LLM resident in VRAM while the forecast runs |
| `handoff` | Existing unload -> forecast -> restore path |
| `block` | Internal fail-closed decision; not accepted as operator input |

COEXIST means **simultaneous residency, not simultaneous inference**. The external
request Gate is drained to exactly zero and CLOSED before the foundation forecast
starts. The Gate is reopened only after the resident LLM and GPU baseline are
verified.

## Safety invariants

1. Forecast MCP request schema is unchanged. The LLM cannot request a residency mode.
2. Residency settings are operator-only configuration.
3. Default mode is `handoff`.
4. Unknown or uncertified profiles fall back to HANDOFF by default.
5. Forced COEXIST without sufficient evidence returns BLOCK.
6. Exact LLM alias, GPU UUID/index, LLM runtime/context, foundation repo/revision,
   and runtime lane must match one certified profile.
7. Foreign GPU processes disqualify AUTO COEXIST.
8. The pre-existing resident LLM GPU PID set must remain stable when available.
9. Post-run used VRAM must return to baseline within the configured tolerance.
10. Holdout, Prospective, and Actual access remain CLOSED.

## Decision formula

Let:

```text
free_before = gpu.memory_free_mib

reserve = max(
  hard_reserve_mib,
  ceil(gpu_total_mib * reserve_ratio),
)

foundation_budget = max(
  minimum_foundation_budget_mib,
  ceil(certified_external_peak_mib * foundation_peak_safety_factor),
)
```

COEXIST is eligible only when:

```text
exact profile match
AND profile.certified == true
AND external peak evidence exists
AND exact LLM identity is live
AND resident LLM GPU PID evidence is present when required
AND foreign GPU process count == 0
AND free_before >= foundation_budget + reserve
```

At the exact threshold, COEXIST is allowed. One MiB below the threshold falls back
to HANDOFF in AUTO or BLOCK in forced COEXIST.

## Configuration

Forecast MCP keeps the residency policy outside the LLM-facing tool contract.

```json
{
  "residency": {
    "mode": "auto",
    "resource_profile_path": "/mnt/e/env/ts/loto_forecast_platform/.runtime/gpu-residency/profiles.json",
    "profile_selector": {
      "llm_alias": "qwen38-27b-ud-iq3xxs-mtp3",
      "llm_runtime": "ik_llama",
      "llm_context_length": 65536,
      "foundation_repo_id": "Salesforce/moirai-2.0-R-small",
      "foundation_revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
      "runtime_lane": "cuda13-experimental"
    },
    "hard_reserve_mib": 2048,
    "reserve_ratio": 0.12,
    "foundation_peak_safety_factor": 1.25,
    "minimum_foundation_budget_mib": 1024,
    "unknown_profile_action": "handoff",
    "require_external_peak_evidence": true,
    "require_exact_llm_identity": true,
    "require_llm_pid_stability_when_available": true,
    "post_run_vram_tolerance_mib": 256
  }
}
```

If the profile path is missing, or there is no exact tuple match, AUTO selects
HANDOFF. This makes it safe to deploy source changes before target-machine
characterization.

## Resource profile schema

```json
{
  "schema_version": 1,
  "profiles": [
    {
      "profile_id": "rtx5070ti-iq3xxs-moirai2-v1",
      "certified": true,
      "gpu": {
        "uuid": "GPU-...",
        "index": 0
      },
      "llm": {
        "alias": "qwen38-27b-ud-iq3xxs-mtp3",
        "runtime": "ik_llama",
        "context_length": 65536,
        "process_names": ["llama-server"]
      },
      "foundation": {
        "repo_id": "Salesforce/moirai-2.0-R-small",
        "revision": "30f43ff08c8494f4943ae1521e9d4e94a0fbb389",
        "runtime_lane": "cuda13-experimental"
      },
      "evidence": {
        "external_peak_vram_mib": 2048,
        "sample_count": 5,
        "certification_run_ids": [
          "gpu-residency-characterize-..."
        ],
        "code_sha256": null
      }
    }
  ]
}
```

`external_peak_vram_mib` is the maximum **incremental external GPU usage above the
resident-LLM baseline**, measured by `nvidia-smi`, not model file size and not a
provider-internal allocator counter.

## State machine

### COEXIST

```text
IDLE
  -> DRAINING
  -> RESIDENCY_DECIDING
  -> COEXIST_READY
  -> FORECAST_RUNNING
  -> FORECAST_STOPPING
  -> LLM_CONTINUITY_CHECK
  -> QWEN_READY
  -> IDLE
```

### HANDOFF

```text
IDLE
  -> DRAINING
  -> RESIDENCY_DECIDING
  -> QWEN_STOPPING
  -> GPU_FREE
  -> FORECAST_RUNNING
  -> FORECAST_STOPPING
  -> QWEN_RESTORING
  -> QWEN_READY
  -> IDLE
```

The library-level forced HANDOFF path delegates directly to the pre-adaptive
`ExclusiveGpuSupervisor` to preserve its established runtime behavior.

## Forecast MCP evidence

`FORECAST_MCP_RESULT.json` contains `gpu_residency` and `timings_ms`.

COEXIST acceptance:

```text
selected_mode=coexist
qwen_stopped=false
qwen_restored=false
llm_continuity_verified=true
foundation CUDA=true
cpu_fallback=false
gate_reopened=true
```

HANDOFF acceptance:

```text
selected_mode=handoff
qwen_stopped=true
qwen_restored=true
gate_reopened=true
```

Performance fields:

```text
residency_decision_ms
gate_drain_ms
llm_unload_ms
llm_reload_ms
foundation_load_ms
forecast_inference_ms
total_tool_latency_ms
```

Some component timings remain `null` when the current provider does not expose a
separate phase measurement. They must not be fabricated.

## Target-machine characterization

Source changes must not automatically modify the live service, Gate, driver, CUDA,
power settings, or model inventory.

Before characterization, the operator must ensure:

```text
selected exact LLM is resident
Gate is CLOSED
in_flight == 0
no unrelated GPU workload
```

Run the same Moirai command 3-5 times with external sampling:

```bash
python scripts/characterize_gpu_residency.py \
  --gpu-index 0 \
  --interval-seconds 0.1 \
  --output .runtime/gpu-residency/run-01.json \
  --llm-alias qwen38-27b-ud-iq3xxs-mtp3 \
  --llm-runtime ik_llama \
  --llm-context-length 65536 \
  --foundation-repo-id Salesforce/moirai-2.0-R-small \
  --foundation-revision 30f43ff08c8494f4943ae1521e9d4e94a0fbb389 \
  --runtime-lane cuda13-experimental \
  -- <exact reviewed provider command>
```

The characterization fails if the command fails, no positive incremental VRAM is
observed, the GPU UUID changes, or the resident GPU PID set changes.

Build/update a certified profile only from multiple PASS evidence files:

```bash
python scripts/certify_gpu_residency.py \
  --registry .runtime/gpu-residency/profiles.json \
  --profile-id rtx5070ti-iq3xxs-moirai2-v1 \
  --min-samples 3 \
  --evidence .runtime/gpu-residency/run-01.json \
  --evidence .runtime/gpu-residency/run-02.json \
  --evidence .runtime/gpu-residency/run-03.json
```

## Verification

Verify a completed Forecast MCP run and its checksums:

```bash
python scripts/verify_gpu_residency_run.py \
  /mnt/e/env/ts/loto_gpu_runs/forecast-mcp/<RUN_ID> \
  --expected-mode coexist
```

Repeat with a deliberately strict reserve configuration to force AUTO -> HANDOFF
without artificially filling VRAM.

The final A/B runtime gate compares the exact same approved provider request under
HANDOFF and COEXIST and requires the same `prediction_sha256`.

## Evidence boundary

GitHub CI can verify contracts, pure decision logic, mocks, configuration, and
source-level safety. It cannot certify:

- target RTX 5070 Ti GPU UUID/PID evidence,
- real external Moirai peak VRAM,
- live Qwen PID continuity,
- real AUTO -> COEXIST selection,
- real AUTO -> HANDOFF selection,
- HANDOFF-vs-COEXIST prediction SHA equivalence.

Those remain `EXECUTION_PENDING` until an exact-head target-machine campaign is
recorded.
