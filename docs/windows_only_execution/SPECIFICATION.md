# Specification — Windows-only formal execution

## Objective

Continue PR #240 from a native-Windows-only operator environment without weakening the scientific or evidence requirements that were previously exercised on Linux.

## Current formal OOF design

Unless deliberately changed before protocol fixation:

```text
formal_games=5
layouts=2
prediction_length=1
context_length=96
outer_folds=5
outer_test_size=20
oof_targets_per_game=100
seeds=42,1729,20260730
best_seed_only=false
primary_metric=hit_at_1
required_baselines=random,fixed,mean,median,last,frequency,statistical_ar1
```

## Stage model

### Stage 8-A — Windows identity audit

- verify final PR head and clean worktree;
- locate the frozen development snapshot;
- verify its SHA-256;
- compute raw-byte code hash;
- record Windows CPU/GPU/RAM/package identity;
- confirm Holdout/Prospective remain closed.

### Stage 8-B — protocol regeneration

Generate 5 games × 2 layouts = 10 new `EvaluationProtocolV2` artifacts in a new evidence directory. Each artifact must bind the final Windows execution identity.

### Stage 8-C — protocol-set fixation

- read all 10 artifacts back;
- verify 10 unique protocol hashes;
- verify design inventory and seed inventory;
- calculate a new `PROTOCOL_SET_SHA256`;
- save index and checksums;
- do not overwrite historical protocol evidence.

### Stage 9 — baseline OOF

For each formal target, generate and seal predictions before reading the target actual. Compare all required baselines under the same protocol.

### Stage 10 — Timer Base 84M OOF

Use the same target set, context boundary, metrics, seed policy, and sealing rules. Reject silent CPU fallback or invalid output.

## Metric output

Primary display order:

1. Hit@±1;
2. position Hit@±1;
3. all-position Hit@±1;
4. MAE;
5. MSE;
6. RMSE.

Multi-seed summaries must include mean, population variance, standard deviation, minimum, maximum, worst value, and worst seed.

## Scientific non-claims

Completion of Windows portability CI does not mean formal model accuracy is verified. No accuracy, champion, promotion, Holdout, or Prospective claim is allowed before the later gates complete.