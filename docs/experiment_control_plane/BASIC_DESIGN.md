# Basic Design

## Proposed package layout

```text
src/loto/experiment_control/
  __init__.py
  canonical.py
  contracts.py
  identifiers.py
  policy.py
  approvals.py
  commands.py
  service.py
  repositories.py
  evidence.py
  projections.py
  errors.py

src/loto/experiment_agent/
  __init__.py
  client.py
  executor.py
  workspace.py
  heartbeat.py
  cancellation.py
  resource_limits.py
  lane_local_gpu.py
  lane_local_cpu.py
  lane_api_paid.py

configs/experiment_control/
  policy_v1.yaml
  evidence_roles_v1.yaml
  lane_profiles_v1.yaml

experiments/
  plans/
  results/

schemas/experiment_control/
  experiment-plan-v1.schema.json
  approval-record-v1.schema.json
  execution-request-v1.schema.json
  evidence-index-v1.schema.json
  result-summary-v1.schema.json

tests/experiment_control/
tests/experiment_agent/
docs/experiment_control_plane/
```

This is a target map, not permission to create all paths in one PR.

## Components

### Canonicalizer

- rejects duplicate JSON/YAML semantic keys;
- normalizes timestamps to UTC RFC3339;
- preserves integer/decimal semantics without float string drift;
- sorts object keys and uses UTF-8 canonical JSON;
- excludes only explicitly derived digest fields;
- returns bytes and SHA-256.

### Plan validator

Validates schema plus cross-field rules such as:

- exact immutable code commit and model revision;
- time-ordered data splits;
- seeds non-empty and unique;
- Hit@±1 primary metric and required baselines/evidence;
- positive, bounded GPU/runtime/API budgets;
- lane-compatible secret/network policy;
- Holdout and Prospective default closed;
- output/evidence storage destinations contain no credentials.

### Approval repository

Stores append-only approval/revocation events. Approval records cannot be edited in place. A correction is a revocation plus a new approval.

### Command service

Implements validate → authorize → idempotency check → persist command/event → return. External projection updates occur after canonical commit through an outbox.

### Lifecycle adapter

If PR #148 is merged, adapt to its canonical lifecycle/lease repository. Otherwise implement only the minimal adapter interface and block production rollout until the shared lifecycle owner is resolved.

### Evidence index

Stores metadata and verification receipts, never credential-bearing URIs or evidence bytes. Verification is repeatable and records verifier version and time source.

### Projection worker

Consumes an outbox and updates GitHub Checks/comments/Project. Projection failure is non-authoritative and retryable.

### Local agent

Polls work, acquires a lease, creates an isolated workspace, verifies inputs, starts a durable child process, emits heartbeat, seals outputs, uploads evidence and submits a terminal result.

## Ownership rules

- No transition enums duplicated from run lifecycle.
- No metric calculations duplicated from evaluation.
- No runtime proof duplicated from runtime certification.
- No trusted timestamp minted outside trusted-time owner.
- No candidate status or promotion transition duplicated from promotion governance.
- No direct writes to PlatformRegistry/MLflow/EventPublisher that bypass the canonical downstream commit owner.
- No Project field taxonomy duplicated from PR #145; experiment fields are mapped into its approved schema or introduced via a separate reviewed change.

## Storage interfaces

```python
class ApprovalRepository(Protocol): ...
class CommandRepository(Protocol): ...
class LifecyclePort(Protocol): ...
class EvidenceIndexRepository(Protocol): ...
class OutboxRepository(Protocol): ...
class ObjectStorePort(Protocol): ...
class GitHubProjectionPort(Protocol): ...
```

Every mutating method accepts an expected revision or idempotency key and returns an immutable receipt.
