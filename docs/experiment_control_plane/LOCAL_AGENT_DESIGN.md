# Local Experiment Agent Design

## Purpose

The Local Agent owns long-running local/API execution. It connects outbound to GitHub or a queue and
requires no public inbound port.

## Components

```text
agent identity
queue client
plan verifier
workspace manager
lane selector
budget guard
executor adapter
heartbeat publisher
cancellation watcher
evidence uploader
GitHub App client
reconciliation worker
```

## Startup gates

- exact agent version and code hash;
- clean host capability inventory;
- plan and approval verification;
- lane permission;
- model/source/runtime eligibility;
- data snapshot availability;
- disk/RAM/GPU availability;
- clock-health policy;
- no duplicate active lease.

## Workspace

Each Run receives an isolated workspace outside the repository. Inputs are read-only. Outputs are
new and never overwrite previous attempts.

## Long-run behavior

- durable state and attempt number;
- periodic heartbeat;
- cancellation check;
- timeout and budget enforcement;
- prediction lock before Actual;
- evidence upload before GitHub completion projection;
- reconciliation after GitHub/API outage.

## Local model lane

Records model revision, weight hash, engine revision, quantization, context, device, PID, VRAM,
throughput, output shape, finite values, and CPU fallback.

## Proprietary API lane

Records model ID, endpoint identity, SDK version, request/response hashes, provider request ID,
tokens, latency, retry, rate limit, and cost. Raw sensitive payload retention follows the plan's
data-minimization policy.
