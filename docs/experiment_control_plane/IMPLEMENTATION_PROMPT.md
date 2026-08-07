# Authoritative Push-Oriented Implementation Prompt

Copy the complete prompt below into a GitHub-capable coding agent. Set exactly one `TARGET_STAGE` per run.

```text
@GitHub

REPOSITORY=https://github.com/arumajirou/loto_forecast_platform
BASE_BRANCH=main
TARGET_STAGE=<plan-contract|approval-ledger|evidence-index|control-service|agent-protocol|execution-lanes|github-projections|control-workflows|evidence-adapters|operational-certification>
PR_MODE=Draft
EXECUTION_MODE=audit-implement-verify-push
DESIGN_PATH=docs/experiment_control_plane

You are the lead engineer responsible for the experiment control, approval and
evidence-index foundation. Read every file under DESIGN_PATH before changing code.
Treat REQUIREMENTS.md, DATA_CONTRACT.md, APPROVAL_MODEL.md,
EVIDENCE_INDEX_CONTRACT.md, IMPLEMENTATION_PLAN.md and TEST_PLAN.md as binding.

## 0. Non-negotiable Git safety

- Fetch repository metadata, default branch and the exact latest main HEAD.
- Inspect git status, branch, remotes and diff before and after changes.
- Create a new stage-specific branch from the exact latest main SHA.
- Do not branch from a documentation/design branch or another implementation PR,
  unless IMPLEMENTATION_PLAN.md explicitly declares a stacked dependency and the
  owner has authorized it.
- Never write directly to main.
- Never force push, rebase published history, reset shared branches, merge,
  enable auto-merge, mark Ready, create a release, delete a branch, or mutate
  production without explicit owner approval.
- Push the implementation branch and open a Draft PR only.

## 1. Mandatory fresh audit before implementation

Re-fetch and record:

1. default branch and latest main SHA;
2. same-name branch and same-purpose open/closed PRs and Issues;
3. matching paths, symbols, schemas, commands and status taxonomies on current main;
4. Issue #58 current state;
5. PRs #121, #123, #124, #125, #129, #135, #137, #138, #141,
   #144, #145, #146, #147, #148 and #151;
6. root pyproject.toml, uv.lock, CI workflows, repository instructions and
   applicable CODEOWNERS/rules;
7. current implementations for configuration, lifecycle, data-access ledger,
   trusted time/Actual, runtime certification, evaluation, telemetry, Projects,
   downstream commit, Registry/PlatformRegistry/MLflow/EventPublisher and promotion.

If latest main already contains the same semantic capability, do not duplicate it.
Report DUPLICATE_FOUND and stop. If an open PR owns the same path or authority,
report OWNERSHIP_CONFLICT and stop or narrow to a non-overlapping adapter after
explicit evidence. Open Draft PR code is read-only design evidence until merged.

## 2. Stage map

- plan-contract -> feat/experiment-plan-contract-v1
- approval-ledger -> feat/experiment-approval-ledger-v1
- evidence-index -> feat/experiment-evidence-index-v1
- control-service -> feat/experiment-control-service-v1
- agent-protocol -> feat/local-experiment-agent-protocol-v1
- execution-lanes -> feat/experiment-execution-lanes-v1
- github-projections -> feat/experiment-github-projections-v1
- control-workflows -> feat/experiment-control-workflows-v1
- evidence-adapters -> feat/experiment-evidence-adapters-v1
- operational-certification -> certify/experiment-control-plane-v1

Implement only the selected stage and its tests/docs. Do not pre-implement later stages.

## 3. Domain invariants

- GitHub is the control/audit projection, not durable execution or full evidence storage.
- Issue labels, comments, reactions, Project fields and editable Issue bodies never
  authorize execution.
- Plan acceptance, EXECUTE, OPEN_HOLDOUT, SCORE_PROSPECTIVE, ACCEPT_RESULT,
  PUBLISH_CAMPAIGN and REQUEST_PROMOTION are separate scopes.
- Every approval binds the exact canonical subject SHA-256 and expires/revokes
  fail-closed.
- Code/config/data/protocol/model revision/seed/budget/lane changes invalidate approval.
- Long execution is leased to a durable agent; GitHub Actions control jobs enqueue
  and exit.
- Every command/side effect is idempotent, journaled, bounded and recoverable.
- GitHub stores no raw data, model weights, large predictions, private keys, API keys,
  bearer tokens or credential-bearing URIs.
- Prediction Lock precedes Actual access. Hit@±1 is primary; MAE/MSE/RMSE,
  position/all-position Hit@±1, required baselines, OOF and multi-seed summaries remain.
- Best seed or first place never implies approval or promotion.
- Consume canonical contracts from their owner; do not redefine lifecycle, evaluation,
  runtime certification, trusted time/Actual, data-access ledger, telemetry,
  downstream commit, Project governance or promotion.

## 4. Engineering requirements

Use the repository's uv project, pyproject.toml, uv.lock, src and tests structure.
Do not pip-install into system Python. Add dependencies only when strictly necessary
and document compatibility. Use strict Pydantic v2 models, type hints and complete
Docstrings for public APIs. Prefer pure functions and injected clock/IO boundaries.

Required controls:

- canonical JSON and duplicate-key rejection;
- expected-revision concurrency and idempotency keys;
- append-only/auditable records;
- bounded timeout/retry/backoff;
- atomic file writes and durable transactions;
- secret masking and allowlisted structured JSON logs;
- OpenTelemetry-compatible correlation when the repository owner contract permits;
- resource limits, cancellation, checkpoint/restart and rollback;
- no unavailable verification represented as PASS.

## 5. Local development gate order

After each meaningful change run only fast owned-path checks:

1. Ruff format/check on changed paths;
2. mypy on changed typed modules;
3. focused pytest;
4. smallest smoke test.

Do not repeatedly trigger heavy GitHub CI during development. At the final local gate,
run compileall, full owned tests, full pytest, coverage, dependency audit, secret scan,
large-file/model/data scan and deterministic artifact verification as applicable.
If a tool is unavailable, record BLOCKED_TOOL_UNAVAILABLE; do not claim success.

For long GPU/API/agent tests, use tmux or a systemd user service, absolute paths,
tee stdout/stderr to logs, persist exit code, install an EXIT trap, and leave an
Enter-key pause for interactive wrappers. Record model/revision/runtime/context,
input/output tokens or shapes, cold/warm timing, GPU PID/VRAM/utilization/temperature/
power and CPU fallback when relevant. Verify load, health, inference, output shape,
finite values, unload and VRAM release.

## 6. Required documentation and artifacts

For the selected stage create/update as applicable:

README, REQUIREMENTS, SPECIFICATION/contract docs, ARCHITECTURE or owned design,
TEST_PLAN, VERIFICATION_REPORT, CHANGELOG, HANDOFF, RUNBOOK,
ARTIFACT_MANIFEST.json and SHA256SUMS.

Preserve failed runs under distinct Run IDs. Include settings, data/code/config hashes,
Git commit, model/revision, seeds, predictions/results, metrics, logs, GPU/runtime
information and evidence references without secrets.

## 7. Push and Draft PR

Before commit:

- inspect status/diff and confirm only owned paths changed;
- scan for secrets, raw data, model weights and oversized files;
- verify generated JSON/YAML and SHA256SUMS;
- capture test commands and exact outcomes.

Create an intentional commit, push the branch, and open a Draft PR against main.
The PR body must include:

STATUS using EXECUTED/VERIFIED/PARTIALLY_VERIFIED/BLOCKED/FAILED,
base and head SHA, branch relation, changed paths, ownership audit, implementation,
local checks with exact counts, remote blob/hash verification, CI classification,
non-claims, rollback and explicit statement that no merge/Ready/auto-merge/production
mutation was performed.

Inspect the workflow run once. If Issue #58's zero-step/no-log pattern recurs, classify
CI_BLOCKED_PRE_RUN, link Issue #58 and do not blindly rerun or modify feature code.

## 8. Stop conditions

Stop without implementation when duplicate ownership, ambiguous canonical authority,
required secret/data access outside scope, unapproved Holdout/Prospective/production
mutation, or unsafe Git operation would be required. Provide evidence and the smallest
safe next action.
```
