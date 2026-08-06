# Execution Lanes

## 1. Lane taxonomy

```text
LOCAL_CPU
LOCAL_GPU
API_PAID
```

A later implementation may add an explicitly reviewed remote private compute lane. Unknown lanes
are rejected.

## 2. Common requirements

Every lane binds:

```text
lane_id
agent_id
host_profile_sha256
code_sha256
config_sha256
data_snapshot_sha256
protocol_hash
model_id
model_revision
resource_budget
deadline
cancellation_policy
evidence_requirements
```

The selected lane cannot silently fall back to another lane.

## 3. LOCAL_CPU

Required evidence:

- CPU model and instruction capabilities;
- operating system and kernel;
- Python and locked dependency identities;
- process PID and thread count;
- memory peak;
- input/output shape and finite values;
- exact runtime duration;
- explicit absence of GPU use.

## 4. LOCAL_GPU

Required evidence:

- GPU model, UUID, driver, CUDA/runtime versions;
- requested and effective device;
- process PID;
- peak VRAM;
- GPU utilization sample summary;
- model revision and weight SHA-256;
- quantization and inference engine identity;
- context length and relevant runtime settings;
- output shape and finite values;
- CPU fallback decision and evidence.

Formal GPU concurrency defaults to one job. CPU worker parallelism is bounded to eight unless a
reviewed plan explicitly lowers it.

## 5. API_PAID

Required controls:

```text
provider
endpoint_class
requested_model
resolved_model_snapshot | null
SDK version
request_count_limit
input_token_limit
output_token_limit
wall_time_limit
cost_limit
retry_limit
rate_limit_policy
circuit_breaker
pricing_snapshot_sha256
```

Required evidence includes provider request IDs, request/response hashes, token counts, latency,
retry count, final cost and reconciliation. Secret values and raw credential-bearing headers are
never persisted.

When the provider does not expose an immutable model snapshot, the run is classified as not fully
reproducible. A mutable model alias must not be represented as a pinned revision.

## 6. Workspace and network

- use a clean per-run workspace;
- verify repository and plan hashes before execution;
- Local LLM inference defaults to offline model snapshots;
- API secrets are exposed only to API_PAID;
- Local CPU/GPU lanes do not receive proprietary API keys;
- unknown PR code never runs on a privileged local runner;
- all output paths are contained under the run workspace.

## 7. Failure and cancellation

A lane reports bounded machine-readable states. Cancellation is cooperative first and forceful only
after a timeout. Partial evidence is retained. A cancellation is not a successful experiment.
