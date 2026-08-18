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

## Local workflow after merge

From Windows PowerShell 5.1:

```powershell
Set-Location 'C:\Users\bp00425\env\ts\loto_forecast_platform'
git switch main
git pull --ff-only origin main

powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  '.\tools\phase7_semantic_diagnosis\run_semantic_diagnosis.ps1'
```

The output is written under:

`evidence/phase7_semantic_diagnosis/<RunId>/`

It includes `DIAGNOSIS.json`, typed/canonical/raw config evidence, trial comparison, environment comparison, artifact manifest, and `SHA256SUMS`.

## GitHub evidence handoff

To hand the local result back through GitHub instead of uploading a ZIP, start from a **clean working tree** and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  '.\tools\phase7_semantic_diagnosis\run_semantic_diagnosis.ps1' `
  -PublishEvidence
```

The launcher creates and pushes a branch named:

`evidence/phase7-semantic-diagnosis-<RunId>`

Only the generated evidence directory is staged and committed. Existing Phase 3/6B/6C/7 raw artifacts are never staged, modified, or deleted.

After the push, report only the branch name (or simply say the run completed). The evidence can then be reviewed directly from GitHub.

## Interpretation

Allowed classifications are:

- `SERIALIZATION_ONLY`
- `DEFAULT_MATERIALIZATION`
- `VERSION_DRIFT`
- `TRUE_CONFIG_DRIFT`
- `UNKNOWN`

This diagnostic intentionally keeps `safe_to_continue_holdout=false` even when serialization-only equivalence is proven. Changing the verifier and resuming Holdout is a separate reviewed action.
