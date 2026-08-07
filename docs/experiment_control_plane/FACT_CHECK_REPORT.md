# Fact Check Report

## Verification status

```text
STATUS=PARTIALLY_VERIFIED
REPOSITORY=arumajirou/loto_forecast_platform
DEFAULT_BRANCH=main
MAIN_SHA=d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0
CHECKED_AT=2026-08-06T18:22:00+09:00
```

Repository metadata, selected repository files, Issue #58, neighboring Draft PR descriptions and primary GitHub documentation were inspected. Live repository Settings, billing, rulesets, Environments, GitHub App registration, Project configuration and local runner host were not accessible and are not represented as verified.

## Current repository facts

- The repository is private, user-owned, and currently uses `main` as the default branch.
- The audited `main` SHA is `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`.
- `README.md` describes six games, 174 registered models, `protocol_hash`, fail-closed evaluation behavior, leakage sentinels and unverified runtime areas.
- `.github/workflows/ci.yml` runs GitHub-hosted CPU CI on `push` and `pull_request`.
- Issue #58 is the canonical open repository-wide blocker for GitHub-hosted jobs failing before workflow step creation. A zero-step run must not be classified as a code-test failure.
- No same-purpose branch, PR, Issue or code-search result for a complete experiment control/approval/evidence-index foundation was found at audit time.

## Neighboring work and mandatory ownership boundaries

| PR / Issue | Current role | This foundation must do |
|---|---|---|
| PR #121 | Strict configuration foundation | consume; do not create a second configuration authority |
| PR #123 | Runtime certification SDK | reference runtime evidence; do not recertify devices |
| PRs #124/#129/#135/#144/#151 | Data Access Ledger, staged pipeline and downstream commit | consume opaque receipts and commit evidence; do not replace the saga |
| PR #125 | Trusted time / Actual source | consume trusted-time and Actual evidence; do not create another clock/source authority |
| PR #137 | Promotion subject and status taxonomy | hand off promotion subjects; do not redefine promotion or activate production |
| PR #138 | Evaluation protocol completeness | consume evaluation reports; do not define a competing metric protocol |
| PRs #141/#147 | Telemetry contracts and OpenTelemetry | emit through their contracts when available; do not fork telemetry semantics |
| PR #145 | GitHub Projects governance foundation | project experiment state into it; do not create a second live Project contract |
| PR #146 | Owner-gated self-hosted GPU CI lane | use only as an optional short control/smoke lane; do not run untrusted PR code |
| PR #148 | Durable run lifecycle contract | use as canonical lifecycle/lease/event foundation if merged; do not duplicate transitions |
| Issue #58 | Actions pre-run infrastructure blocker | classify CI separately and avoid blind reruns |

All listed PRs were open Drafts at audit time. Their code is not part of `main` until merged. Each implementation PR must re-check current state and either integrate the merged contract, use a read-only compatibility adapter, or stop on ownership conflict.

## Official GitHub capability checks

| Capability | Verified official behavior | Design consequence |
|---|---|---|
| `workflow_dispatch` | The workflow must exist on the default branch before manual dispatch is available; up to 25 inputs are supported. | Merge the short control workflow before relying on dispatch. Never treat a workflow only on an experiment branch as dispatchable authority. |
| Self-hosted runner | The runner connects outbound over HTTPS 443. GitHub recommends ephemeral runners for autoscaling and assigns one job to an ephemeral runner before automatic deregistration. | No inbound public endpoint is required. Preserve runner logs externally and wipe workspaces. |
| GitHub App installation token | Installation tokens expire after one hour and can be further repository/permission scoped. | Prefer short-lived App tokens over long-lived PATs. Refresh safely; never store tokens in plans or evidence. |
| Checks API | Check-run write operations are available to GitHub Apps; checks can carry rich status and annotations. | Use a dedicated App as the status bridge; GitHub Checks are projections, not the evidence source of truth. |
| Projects | Projects support custom fields, views, built-in workflows, API and Actions automation; a project can use up to 50 total fields. | Reuse PR #145's governance Project and add only approved experiment projections. |
| Issue Forms | YAML issue forms support typed inputs and validations, but remain public preview and issue bodies remain editable. | Treat Issue Forms as intake, never as the immutable experiment contract. |
| Rulesets | Rulesets can require PRs, status checks, block force pushes and select an expected GitHub App source for a required check. | Activate only after checks have reported successfully and rollback is tested. |
| Actions artifact retention | Private-repository artifacts/logs are configurable from 1 to 400 days and are coupled to workflow retention. | Use artifacts for transport/diagnostics only, not permanent evidence. |
| Environments | Required reviewers and protection features depend on repository visibility and plan. | Do not assume private-repository manual gates exist. Verify plan first and provide an application-level approval fallback. |

## Corrections and clarifications applied

1. **Plan PR merge is plan acceptance, not execute authorization.** Execution requires a separate exact-subject approval and explicit dispatch/enqueue action.
2. **A label is intake metadata only.** It must never directly authorize GPU or paid API execution.
3. **Actions is a control-job host, not a durable multi-day executor.** Long execution lives behind a leased local agent or equivalent durable worker.
4. **GitHub Project status is a projection, not canonical lifecycle state.** Canonical lifecycle/event data remains in the lifecycle repository.
5. **GitHub Releases are campaign-level.** Trials remain in MLflow/DB; runs receive result manifests; only approved campaigns or Prospective bundles become releases.
6. **GitHub artifacts are not immutable archives.** External object storage plus digest/signature evidence is required.
7. **Private-repository Environment approval cannot be assumed.** Feature/plan availability must be verified before rollout.

## Primary official references

See `SOURCE_REGISTRY.md` for exact official URLs and the claim mapped to each source.
