# Requirements — GitHub Platform Features Foundation v1

## 1. Goals

- Add controlled GitHub Pages, Dependabot, Projects, Webhooks, and security-scanning capabilities.
- Preserve strict evidence boundaries, reproducibility, secret safety, and no-silent-fallback behavior.
- Make every feature independently deployable and independently reversible.
- Keep existing prediction, evaluation, registry, promotion, and production bindings unchanged in the foundation phase.

## 2. Constraints

- Issue #58 currently blocks actionable GitHub Actions execution before step creation.
- The repository is private and currently owned by a personal account; Pages visibility and CodeQL eligibility require explicit owner review.
- Root Torch, Triton, Transformers, NeuralForecast, Python, and CUDA compatibility must not be changed by an infrastructure-only PR.
- No Holdout or Prospective values may be opened or published.
- No secret value, webhook callback URL, token, private registry URL, or local credential path may enter Git history or Pages output.
- No auto-merge, force push, history rewrite, branch deletion, or direct write to `main`.

## 3. Functional requirements

### FR-GH-001 — Actions prerequisite gate

The implementation must detect and document whether a GitHub-hosted job reaches workflow step creation. Actions-dependent features remain `BLOCKED` while Issue #58 is unresolved.

### FR-GH-002 — Dependabot

- Add `.github/dependabot.yml` on a dedicated PR.
- Configure `uv` for the repository root.
- Configure `github-actions` for `/.github/workflows`.
- Use weekly cadence and bounded open PR counts.
- Attach dependency/security/compatibility labels when available.
- Do not automatically merge dependency PRs.
- Separate major updates from routine compatible updates where supported.
- Require frozen lock validation, dependency review, focused tests, and relevant runtime smoke checks before approval.

### FR-GH-003 — GitHub Projects

- Define status, workstream, type, priority, evidence status, PR phase, provider, risk, base SHA, protocol hash, and target release fields.
- Auto-add repository Issues and PRs using built-in Project workflows where possible.
- Represent `PROPOSED`, `EXECUTION_PENDING`, `EXECUTED`, `VERIFIED`, `PARTIALLY_VERIFIED`, `BLOCKED`, and `FAILED` without collapsing states.
- Never treat a Project field as authoritative model-registry or production-promotion state.

### FR-GH-004 — GitHub Pages

- Build from `docs-public/` only.
- Fail when internal files, secrets, local absolute paths, Holdout/Prospective evidence, or unapproved artifacts are included.
- Run strict documentation build on pull requests.
- Deploy only from `main` after approval.
- Use least-privilege workflow permissions and the `github-pages` environment.
- Remain disabled until site visibility is explicitly approved.

### FR-GH-005 — Webhook receiver

- Provide `POST /api/v2/integrations/github/webhook`.
- Validate `X-Hub-Signature-256` with HMAC-SHA256 and constant-time comparison.
- Require `X-GitHub-Delivery` and `X-GitHub-Event`.
- Reject missing, malformed, oversized, stale, or invalidly signed requests.
- Persist only masked, bounded, schema-validated event metadata.
- Deduplicate by delivery ID and payload SHA-256.
- Return a 2xx acknowledgement before expensive processing.
- Process supported events asynchronously through a durable queue or transactional outbox.
- Support bounded retry, dead-letter state, audit log, timeout, and rollback.
- Initial event allowlist: `push`, `pull_request`, `issues`, `workflow_run`.

### FR-GH-006 — Notification adapters

- Email is the default notification adapter.
- Slack remains optional and disabled by default.
- Notification failure must not change the authoritative GitHub or platform state.
- Notifications contain references and status only; no secret or raw model artifact payloads.

### FR-GH-007 — MLflow linkage

Webhook processing may record Git commit SHA, Run ID, artifact URI, protocol hash, prediction-lock hash, manifest SHA-256, workflow identity, and verification status. It must not upload arbitrary GitHub payloads or mutate promotion state.

### FR-GH-008 — Security scanning

- Use CodeQL only when repository ownership, plan, and GitHub Code Security eligibility are verified.
- Until then, use OSS scanners with an explicit `FALLBACK_NOT_CODEQL` status.
- Retain SARIF/JSON reports, tool versions, exit codes, manifests, and SHA-256 evidence.
- Scanners must include dependency, Python static analysis, and secret detection coverage.

## 4. Non-functional requirements

- **Security:** least privilege, fail closed, secret masking, no callback URL disclosure.
- **Reliability:** idempotency, bounded retries, queue durability, deterministic status transitions.
- **Observability:** JSON logs, Prometheus metrics, trace IDs, delivery IDs, workflow IDs, Run IDs.
- **Performance:** webhook acknowledgement target under 2 seconds; hard limit below GitHub's 10-second delivery timeout.
- **Reproducibility:** record Git SHA, configuration SHA-256, workflow revision, tool versions, and timestamps in UTC.
- **Maintainability:** Pydantic contracts, typed public APIs, dedicated modules, focused tests, documented rollback.
- **Compatibility:** no root dependency change unless a feature PR proves it is necessary and compatible.

## 5. Acceptance criteria

The foundation documentation is accepted when all design documents exist, cross-reference one another, identify verified facts and blockers, define separate implementation PRs, and make no execution claim.

An implementation feature is accepted only when its focused tests pass locally, relevant negative tests pass, artifacts verify, secrets are absent, and an actionable GitHub Actions run with visible steps succeeds after Issue #58 is resolved.