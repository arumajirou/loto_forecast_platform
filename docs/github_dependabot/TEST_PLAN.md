# Test Plan — GitHub Dependabot Foundation v1

## Objectives

- Prove the configuration contains only the approved ecosystems.
- Prove schedules and open-PR limits are bounded.
- Keep compatibility-sensitive Python dependencies out of routine groups.
- Prove no auto-merge or private-registry credential configuration is introduced.
- Distinguish static configuration review from GitHub runtime acceptance.

## Static and focused checks

The repository-owned test is:

```text
tests/github_platform/test_dependabot_config.py
```

Required focused command:

```bash
uv run pytest -q tests/github_platform/test_dependabot_config.py
```

Additional local checks:

```bash
uv run ruff format --check tests/github_platform/test_dependabot_config.py
uv run ruff check tests/github_platform/test_dependabot_config.py
uv run python -m compileall -q tests/github_platform
```

Expected assertions:

1. top-level Dependabot version is `2`;
2. configured ecosystems are exactly `uv` and `github-actions`;
3. both entries use `directory: "/"`;
4. both entries are weekly, Monday, Asia/Tokyo;
5. open version-update PR limits are three and two respectively;
6. routine groups include only minor and patch updates;
7. compatibility-sensitive Python dependencies are excluded from routine grouping;
8. no auto-merge term, registry, token, or password is present.

## Negative review cases

The focused test must fail when any of these changes is introduced:

- an unapproved package ecosystem;
- an unbounded or missing open-PR limit;
- daily update cadence;
- a sensitive dependency removed from the exclusion set;
- major releases added to a routine group;
- private registry or credential keys;
- auto-merge configuration text.

## GitHub acceptance checks

After the PR is merged to the default branch:

1. open Insights → Dependency graph → Dependabot;
2. confirm both ecosystems are parsed without configuration errors;
3. retain Dependabot job-log evidence for both ecosystems;
4. retain the first generated PR URLs and exact manifest/lock diffs;
5. verify default labels and grouped-versus-individual behavior;
6. run frozen-lock and focused compatibility checks on generated PR heads.

## CI boundary

Issue #58 currently prevents reliable GitHub-hosted execution. A job with `steps=null`, an empty
step list, or unavailable logs is `ACTIONS_BLOCKED_PRE_RUN`, not a test failure and not a pass.
Do not repeatedly rerun an unchanged zero-step job.

## Final quality gate

After local focused checks pass and the change stabilizes, run the repository's full test suite
once. Run GitHub Actions once only after the administrative condition tracked by Issue #58 has
materially changed. Record commands, UTC times, tool versions, exit codes, Git SHA, and artifacts.
