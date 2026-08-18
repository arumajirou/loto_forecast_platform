# Phase 7 semantic-config diagnosis

This repository tool performs the **development-only, pre-Holdout forensic replay** needed to diagnose the seed=1 semantic-config SHA mismatch from Phase 7.

## Scientific safety contract

The tool must keep all of the following true:

- `holdout_draws_accessed = 0`
- `actuals_accessed = 0`
- Candidate Freeze is read-only
- `phase7_holdout.py` is read-only
- no Holdout scoring
- no candidate reselection
- no new HPO for model selection
- no expected-hash replacement
- no verifier weakening

The frozen experiment source commit remains:

`179bcbc9a51a60f0badfe7faa25f3818ab686229`

The **current repository HEAD is allowed to be newer**. The diagnosis verifies that the frozen experiment commit exists in the checkout and is an ancestor of the current HEAD, while it replays the frozen Phase 7 runner by its exact SHA-256. This makes the tool installable on current `main` without changing the frozen experiment authority.

## Windows worktree safety

The repository contains historical tracked evidence paths with `:` in names such as `baseline:fixed`, which Git for Windows cannot materialize. A Windows checkout may therefore report invalid-path errors or show unrelated tracked files as deleted even though the Phase 7 tool itself is present.

The diagnosis launcher deliberately does **not** repair, reset, clean, stage, or switch the user's primary worktree. In particular it does not run `git reset --hard`, `git clean`, `git switch -c`, `git add`, `git commit`, or `git push` against the local checkout.

Legitimate local edits may remain in the primary worktree. They are not part of the Phase 7 evidence publication flow.

## Local workflow

From Windows PowerShell 5.1, run the merged launcher from the repository. The launcher only needs the repository metadata and tool files; it does not require a clean working tree.

```powershell
Set-Location 'C:\Users\bp00425\env\ts\loto_forecast_platform'

powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  '.\tools\phase7_semantic_diagnosis\run_semantic_diagnosis.ps1'
```

By default, local output is written **outside the repository** under:

`C:\Users\bp00425\Downloads\automlforecast-phase7-semantic-diagnosis-<RunId>\`

It includes `DIAGNOSIS.json`, typed/canonical/raw config evidence, trial comparison, environment comparison, artifact manifest, and `SHA256SUMS`.

Use `-OutputRoot <path>` to place the run directory under a different external root.

## GitHub evidence handoff

`-PublishEvidence` publishes the generated evidence without changing the primary worktree:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  '.\tools\phase7_semantic_diagnosis\run_semantic_diagnosis.ps1' `
  -PublishEvidence
```

Requirements for publication only:

- GitHub CLI `gh` is installed.
- `gh auth status` succeeds.
- the authenticated account can push to `arumajirou/loto_forecast_platform`.

The launcher uses GitHub's Git Data API through `gh api` to create, server-side:

1. one Git blob per generated evidence file,
2. a tree based on the current remote `main` tree,
3. an evidence commit whose parent is the current remote `main` commit,
4. `refs/heads/evidence/phase7-semantic-diagnosis-<RunId>`.

The remote evidence path is restricted to:

`evidence/phase7_semantic_diagnosis/<RunId>/`

No local branch switch, staging, commit, or push occurs. Existing Phase 3/6B/6C/7 raw artifacts and unrelated local modifications are never uploaded.

After publication, report the emitted `EVIDENCE_BRANCH` value (or simply say the run completed). The evidence can then be reviewed directly from GitHub.

## Interpretation

Allowed classifications are:

- `SERIALIZATION_ONLY`
- `DEFAULT_MATERIALIZATION`
- `VERSION_DRIFT`
- `TRUE_CONFIG_DRIFT`
- `UNKNOWN`

This diagnostic intentionally keeps `safe_to_continue_holdout=false` even when serialization-only equivalence is proven. Changing the verifier and resuming Holdout is a separate reviewed action.
