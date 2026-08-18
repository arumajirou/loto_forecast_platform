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

## Fail-closed behavior

Derivation fails unless the original runner SHA and canonical serializer Git blob match exactly. Every source patch anchor must occur exactly once. The output directory must not already exist. The generated runner and copied serializer must compile successfully.

Runtime replay fails on MLForecast version drift, malformed frozen config, unsupported semantic config state, or canonical frozen/replay mismatch.

## Usage

```powershell
python tools/phase7_holdout_runner/derive_canonical_runner.py `
  --runner C:\path\to\phase7_holdout.py `
  --semantic-config-source src\loto\evaluation\semantic_config.py `
  --output-dir C:\path\to\new-derived-runner-bundle
```

The output bundle contains the derived runner, a pinned copy of the semantic serializer, and `DERIVED_RUNNER_MANIFEST.json` with the original and derived identities.

This tool does not execute Holdout, read Holdout actuals, score predictions, alter Candidate Freeze, or overwrite the original runner.
