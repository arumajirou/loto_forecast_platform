# Requirements — GitHub Dependabot Foundation v1

## Functional requirements

### DEP-FR-001 — Supported ecosystems

The configuration must monitor the root `uv` manifest/lock and GitHub Actions workflow references.
No other ecosystem is enabled in this foundation increment.

### DEP-FR-002 — Bounded cadence

Each ecosystem must run weekly at an explicit Asia/Tokyo time and must define a bounded maximum
number of open version-update pull requests.

### DEP-FR-003 — Compatibility isolation

Routine minor and patch updates may be grouped. Major updates and compatibility-sensitive Python
packages must remain individual pull requests so reviewers can isolate manifest, lock and runtime
impact.

### DEP-FR-004 — Human approval

The configuration must not add auto-merge. Every generated PR requires human review, frozen-lock
validation, focused tests and relevant runtime smoke evidence before merge.

### DEP-FR-005 — Secret safety

The foundation must not configure private registries, tokens, passwords, callback URLs or other
credential values.

### DEP-FR-006 — Authority boundary

Dependabot-created PRs must not automatically mutate model registry, promotion, approval, canary,
production binding, evaluation protocol, prediction locks, Holdout, Prospective or raw data.

### DEP-FR-007 — Evidence status

Configuration presence is `EXECUTED`, not `VERIFIED`. Runtime acceptance requires successful
Dependabot parsing/job evidence on the default branch and generated PR evidence.

### DEP-FR-008 — Rollback

The feature must be reversible through a normal reviewed PR that removes the dedicated
configuration, tests and documentation. Existing generated PRs must be handled explicitly.

## Non-functional requirements

- **Security:** no credential material and no unattended merge authority.
- **Reliability:** bounded schedules and update volume.
- **Reproducibility:** retain base/head SHAs, exact configuration and evidence identities.
- **Maintainability:** repository-owned configuration tests and operational documentation.
- **Compatibility:** no dependency or lock update in the foundation PR.
- **Observability:** Dependabot job logs and generated PR URLs are required after activation.

## Acceptance criteria

The implementation PR is locally complete when:

1. owned files exist and the diff is limited to the approved paths;
2. the configuration satisfies the repository-owned policy test;
3. no manifest, lock, source runtime, registry or existing workflow file changed;
4. docs describe review, failure classification and rollback;
5. unexecuted checks and Issue #58 are reported without unsupported success claims.

The feature becomes runtime-verified only after the configuration is present on the default branch,
Dependabot parses both ecosystems successfully, and the first generated PR behavior is inspected.
