# Runbook — GitHub Dependabot Foundation v1

## Purpose

Operate, verify, pause, and roll back Dependabot version updates without granting merge authority or
changing model-governance state.

## Pre-merge review

1. Confirm the branch derives from the recorded `main` SHA.
2. Confirm changed files remain within the owned-path allowlist.
3. Confirm `pyproject.toml`, `uv.lock`, and `.github/workflows/ci.yml` are unchanged.
4. Run the focused configuration test and static Python checks.
5. Scan the diff for tokens, passwords, private registry URLs, callback URLs, and local paths.
6. Keep the PR Draft while GitHub acceptance and Issue #58 remain unresolved.

## Activation

Dependabot reads `.github/dependabot.yml` from the default branch. Merging the implementation PR is
the activation event; no separate credential is required for public package registries.

After activation:

1. open **Insights → Dependency graph → Dependabot**;
2. inspect configuration errors and job logs for `uv` and `github-actions`;
3. retain the first successful parse/job evidence;
4. record the first generated update PR for each ecosystem;
5. verify PR grouping, labels, schedule, and open-PR bounds.

Configuration presence alone is not runtime verification.

## Generated PR triage

For each Dependabot PR:

1. classify dependency ownership and compatibility risk;
2. review release notes, provenance, license, and known breaking changes;
3. inspect manifest and lock diffs;
4. run `uv sync --frozen` on the exact PR head;
5. run focused tests and relevant runtime smoke tests;
6. verify CPU/GPU, Python and framework compatibility when applicable;
7. record Issue #58 separately if CI fails before step creation;
8. do not auto-merge.

Sensitive dependencies excluded from routine groups must remain individual PRs. Do not combine them
manually without a separate compatibility plan.

## Pause procedures

To pause one ecosystem, set its `open-pull-requests-limit` to `0` in a normal reviewed PR. To pause
one dependency, add a narrowly justified `ignore` rule with a removal condition and owner. Do not
silently close security update coverage.

## Rollback

The complete rollback is a normal PR that removes:

```text
.github/dependabot.yml
tests/github_platform/test_dependabot_config.py
docs/github_dependabot/
```

After merge, verify that version-update jobs stop. Existing Dependabot PRs remain ordinary GitHub
PRs and must be closed or retained explicitly; rollback does not merge or delete them automatically.

## Incident handling

### Configuration parse failure

- retain the Dependabot job error;
- compare the exact default-branch file with the official options reference;
- correct only the invalid option in a focused Draft PR;
- do not claim the ecosystem is monitored until a successful parse is observed.

### Excessive update volume

- confirm open-PR limits are being enforced;
- close or merge existing PRs only after review;
- adjust grouping or limits in a separate PR;
- do not enable auto-merge as a volume workaround.

### CI fails before steps

- classify as `ACTIONS_BLOCKED_PRE_RUN` when steps and logs are absent;
- reference Issue #58;
- do not alter dependency or workflow content without a concrete code-level failure;
- rerun only after an administrative condition changes.

### Lock or runtime incompatibility

- do not merge;
- document the failing package combination and exact head SHA;
- split grouped updates if needed;
- preserve the existing production, registry, promotion and prediction-lock state.
