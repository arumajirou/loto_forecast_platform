# Requirements

## 1. Goals

- Make every experiment traceable from hypothesis through result review.
- Bind every run to exact code, configuration, data, model, evaluation, seed, and budget identities.
- Separate approval from execution.
- Separate GitHub desired state from local/API execution state.
- Prevent a label, comment, or unreviewed branch from starting protected work.
- Maintain a compact GitHub evidence index without duplicating full MLflow/DB/Object Storage data.
- Support local CPU, local GPU, local LLM, and proprietary API lanes.
- Preserve the platform's evaluation and leakage-control policies.

## 2. Functional requirements

### Experiment intake and plan

- **FR-001**: Provide an Issue Form for human-friendly experiment proposals.
- **FR-002**: Treat a strict reviewed `ExperimentPlan` file as the formal contract.
- **FR-003**: Bind plan identity to Issue, code SHA, data snapshot, protocol hash, models, revisions,
  seeds, resource budget, and protected-stage policy.
- **FR-004**: Reject implicit defaults that affect results.
- **FR-005**: Reject mutable/unpinned model or code revisions for formal runs.
- **FR-006**: Require Hit@±1 as primary metric and the complete secondary metric inventory.
- **FR-007**: Require Random, fixed, mean, median, last, frequency, and statistical baselines.
- **FR-008**: Require all approved seeds and mean, population variance, and worst value.
- **FR-009**: Prohibit best-seed-only and first-place-only adoption.

### Approval

- **FR-010**: Separate proposal, plan review, execution authorization, paid-API authorization,
  Holdout authorization, Prospective lock authorization, and result acceptance.
- **FR-011**: Bind approval to plan SHA-256, scope, approver identity, and expiration/one-time-use
  policy.
- **FR-012**: A changed plan invalidates prior approval.
- **FR-013**: Experiment approval cannot authorize Registry, Promotion, canary, or primary binding.
- **FR-014**: Self-approval constraints must be explicit; where the GitHub plan cannot enforce them,
  the system reports the limitation instead of claiming enforcement.

### Dispatch and execution

- **FR-015**: Use short GitHub control jobs for validation and enqueue only.
- **FR-016**: Long-running execution is owned by an outbound-only Local Experiment Agent.
- **FR-017**: A label or comment cannot directly start an execution.
- **FR-018**: Use deterministic Run ID and dispatch idempotency key.
- **FR-019**: Support cancel, resume, heartbeat, lease, fencing, and retry through PR #140 lifecycle
  contracts after they are available.
- **FR-020**: Enforce lane separation: local CPU, local GPU, and paid API.
- **FR-021**: Cap local concurrency at eight workers and serialize formal GPU jobs unless an
  explicitly reviewed resource plan says otherwise.
- **FR-022**: Enforce API request, token, time, and cost budgets before credentials are exposed.

### GitHub App and checks

- **FR-023**: Use a least-privilege GitHub App for automated Checks, comments, and Project updates.
- **FR-024**: Use one-hour installation tokens, never a long-lived PAT in the agent.
- **FR-025**: Publish bounded Check Run names and states.
- **FR-026**: Preserve external details URLs to MLflow/Grafana/Evidence UI without copying secrets.
- **FR-027**: Required checks may be restricted to the GitHub App as the accepted source when
  repository rules support it.

### Evidence index

- **FR-028**: Store GitHub-safe metadata and summaries only.
- **FR-029**: Store large or sensitive artifacts outside GitHub.
- **FR-030**: Every indexed artifact must include URI, size, SHA-256, media type, producer, and
  verification status.
- **FR-031**: Bind Prediction Lock before Actual availability.
- **FR-032**: Bind Actual source and Actual Lock after publication.
- **FR-033**: Retain runtime certification, leakage, evaluation protocol, multi-seed, baseline, and
  cost evidence references.
- **FR-034**: Distinguish `INDEXED`, `REMOTE_VERIFIED`, `MISSING`, `HASH_CONFLICT`, and `REVOKED`.
- **FR-035**: GitHub Actions artifacts cannot be the sole permanent evidence source.

### Projects and reporting

- **FR-036**: Project fields are a status projection, not scientific authority.
- **FR-037**: Project synchronization must be idempotent and exportable.
- **FR-038**: Trials stay in MLflow/DB; Runs receive Checks and manifests; Campaigns may receive
  protected tags/releases.
- **FR-039**: Result PRs contain summaries and evidence indexes, not huge binary artifacts.
- **FR-040**: GitHub Pages, if used, publishes only reviewed non-sensitive campaign summaries.

## 3. Non-functional requirements

- Pydantic v2 strict, frozen, `extra="forbid"`, finite-number validation.
- Canonical UTF-8 JSON and lowercase SHA-256.
- UTC timestamps and explicit trusted-time status.
- Least privilege and secret minimization.
- Idempotent API and Project operations.
- Bounded labels and Check names.
- Offline-capable local execution.
- No public inbound port required on the local machine.
- All unexecuted gates remain `NOT_EXECUTED` or `BLOCKED`.
- Documentation and machine-readable contracts remain synchronized.
