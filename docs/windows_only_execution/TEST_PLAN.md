# Test Plan — Windows-only execution

## Gate 1 — repository and PR identity

- fetch the target branch;
- verify PR remains open/draft;
- verify exact expected head before formal evidence generation;
- require a clean isolated worktree;
- preserve unrelated local files.

## Gate 2 — Windows environment

Verify:

- PowerShell 7 available;
- `uv` available;
- required managed Python available;
- GitHub authentication for required read/write actions;
- Windows runner service healthy when CI is used;
- GPU/resource inventory can be measured.

## Gate 3 — data identity

- locate frozen development snapshot;
- verify all existing checksum manifests;
- verify expected development snapshot SHA-256;
- verify snapshot scope is development-only;
- assert Holdout/Prospective remain unopened;
- do not query a database to substitute missing snapshot evidence.

## Gate 4 — final protocol fixation

- compute final Git commit;
- compute raw-byte `git ls-tree` SHA-256;
- measure Windows package/resource identity;
- regenerate 10 `EvaluationProtocolV2` artifacts;
- read all artifacts back;
- verify 10 unique protocol hashes;
- calculate and persist new protocol-set SHA-256;
- refuse overwrite of historical artifacts.

## Gate 5 — baseline OOF

For every formal target:

- build context strictly before target draw;
- generate all required baselines;
- seal every prediction before actual read;
- verify seals;
- read target actual;
- score Hit@±1 first plus all required metrics.

For random baseline, execute all configured seeds and keep all seed outputs.

## Gate 6 — Timer Base 84M runtime

Before scoring accuracy, verify:

- model load;
- request input contract;
- `actuals_used=false` during prediction;
- inference success;
- output shape;
- finite predictions;
- intended device;
- GPU PID/VRAM when applicable;
- no unrecorded CPU fallback.

Then apply the same target/scoring/sealing conditions as the baselines.

## Gate 7 — aggregation and comparison

For every metric and seed inventory:

- count;
- mean;
- population variance;
- standard deviation;
- minimum;
- maximum;
- worst value;
- worst seed.

Compare Timer and all required baselines under exactly the same formal protocol.

## Gate 8 — protected partitions

Do not open Holdout or Prospective merely because OOF completes. They require separate explicit authorization and new evidence boundaries.

## Validation order

Focused tests and smoke tests first. Run heavy repository-wide tests/CI only after implementation/evidence changes are stable.