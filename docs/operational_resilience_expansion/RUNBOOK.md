# Runbook

## 1. Before each implementation PR

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

git status --short
git remote -v
gh repo view arumajirou/loto_forecast_platform \
  --json defaultBranchRef,nameWithOwner
gh api repos/arumajirou/loto_forecast_platform/commits/main \
  --jq '.sha'
gh pr list --repo arumajirou/loto_forecast_platform \
  --state open --limit 200
gh issue list --repo arumajirou/loto_forecast_platform \
  --state open --limit 200
```

Do not modify a dirty worktree. Create a new worktree or clean isolated clone from the exact
re-fetched main SHA.

## 2. Focused validation template

```bash
uv sync --extra dev
uv run ruff check <changed-python-paths>
uv run mypy <changed-package-paths>
uv run python -m compileall <changed-package-paths> <changed-tests>
uv run pytest -q <focused-tests>
```

Run full pytest only after implementation and focused smoke stabilize.

## 3. Artifact verification

```bash
sha256sum -c SHA256SUMS
git diff --check
git status --short
```

Verify that the tested local bytes equal the published Git blobs.

## 4. CI classification

When Actions fails:

1. inspect workflow run;
2. inspect job list;
3. inspect created steps;
4. fetch logs;
5. classify as code failure only when an actionable command/trace exists;
6. do not blind-rerun issue #58 behavior.

## 5. Target-host safety

- use a non-production PostgreSQL DSN;
- refuse hostnames or database names matching production allow/deny policy;
- use an external artifact workspace;
- cap CPU threads at 8;
- run one GPU job at a time;
- record free disk, RAM, GPU, driver, CUDA, PID, and process list;
- retain Enter-to-exit wrapper for operator sessions.

## 6. Stop immediately when

- main moved after the audit and before branch creation;
- duplicate purpose or path owner appears;
- protected Actual data becomes accessible;
- unknown schema would be stamped or modified;
- a secret appears in output;
- a stale fencing token is accepted;
- migration downgrade fails;
- sandbox effective controls cannot be observed;
- fault harness points to a non-ephemeral service;
- hash or manifest verification fails.
