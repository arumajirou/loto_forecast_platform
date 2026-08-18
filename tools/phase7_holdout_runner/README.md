# Phase 7 Holdout canonical runner derivation

This tool derives a new Holdout runner from the sealed historical Phase 7 runner without modifying the original file.

## Fixed inputs

- Original runner SHA-256: `986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187`
- Canonical serializer Git blob: `52949291c563d1126e3dd6d1363305c5766a630d`
- Canonical schema: `loto.semantic-config/v1`
- Required MLForecast version: `1.1.0`
- Explicit legacy `Differences` state: `differences=[1]`

## What changes

The derived runner keeps the legacy process-dependent semantic SHA as audit evidence, but it no longer uses legacy SHA equality as the semantic gate. It instead compares canonical v1 hashes of the frozen config and the live replay config.

The existing frozen trial SHA checks, frozen config file SHA checks, trial sequence verification, Candidate Freeze checks, sequential prediction lock chain, and lock-before-actual ordering remain untouched.

The derived replay evidence adds:

- `legacy_semantic_sha256_expected`
- `legacy_semantic_sha256_replay`
- `legacy_semantic_hash_match`
- `canonical_semantic_schema`
- `canonical_semantic_sha256_frozen`
- `canonical_semantic_sha256_replay`
- `canonical_semantic_match`
- `mlforecast_version`

## Replay-only verification

The derived runner adds `--stop-after-replay`. When this flag is present, the runner performs the original frozen 4-seed/80-trial replay verification plus canonical semantic v1 verification, writes `REPLAY_ONLY_VERIFICATION.json`, updates progress to `REPLAY_VERIFIED_CANONICAL_V1`, and exits successfully **before** entering the sequential Holdout loop.

The replay-only path records:

- `holdout_draws_accessed: 0`
- `actuals_accessed: 0`
- `holdout_executed: false`

This mode exists specifically to satisfy the TAJ-67 pre-Holdout verification gate. It must be used before any full Holdout execution.

## Fail-closed behavior

Derivation fails unless the original runner SHA and canonical serializer Git blob match exactly. Every source patch anchor must occur exactly once. The output directory must not already exist. The generated runner and copied serializer must compile successfully.

The derivation also re-reads the original runner and serializer source after bundle creation and fails if either changed during derivation.

Runtime replay fails on MLForecast version drift, malformed frozen config, unsupported semantic config state, or canonical frozen/replay mismatch.

## Usage

```powershell
python tools/phase7_holdout_runner/derive_canonical_runner.py `
  --runner C:\path\to\phase7_holdout.py `
  --semantic-config-source src\loto\evaluation\semantic_config.py `
  --output-dir C:\path\to\new-derived-runner-bundle
```

The output bundle contains the derived runner, a pinned copy of the semantic serializer, and `DERIVED_RUNNER_MANIFEST.json` with the original and derived identities.

After derivation, the required first execution is replay-only:

```powershell
python C:\path\to\new-derived-runner-bundle\phase7_holdout_canonical_v1.py `
  --development <development.csv> `
  --canonical <canonical.csv> `
  --phase6c-root <phase6c-root> `
  --artifacts <new-replay-only-artifact-dir> `
  --freeze-sha256 deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c `
  --git-commit 179bcbc9a51a60f0badfe7faa25f3818ab686229 `
  --stop-after-replay
```

The derivation tool itself does not execute Holdout, read Holdout actuals, score predictions, alter Candidate Freeze, or overwrite the original runner.
