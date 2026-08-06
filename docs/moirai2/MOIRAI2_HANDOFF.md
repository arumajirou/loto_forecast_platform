# Moirai 2.0 Handoff

The current stack is PR #83, #86, #87, #89, #91, #98, followed by P8D. Keep every PR Draft.
Do not merge, retarget, force-push, delete branches, or open OOF before the target-host sequence passes.

## Prepare the control workspace

Use the same clean source commit and one pinned local snapshot for both lanes. The workspace must be
outside the repository so P8C can still prove a clean worktree.

```bash
RUN_ID="moirai2-p8d-$(date +%Y%m%d-%H%M%S)"
WORKSPACE="/mnt/e/env/logs/moirai2-target/${RUN_ID}"
SNAPSHOT="/absolute/path/to/Salesforce-moirai-2.0-R-small"

uv run python scripts/prepare_moirai2_target_execution.py \
  --run-id "$RUN_ID" \
  --snapshot-path "$SNAPSHOT" \
  --workspace-dir "$WORKSPACE"

cat "$WORKSPACE/control/P8D_OPERATOR_COMMANDS.md"
```

## Execute only the next recorded stage

Follow the generated commands in order. Inspect each lock candidate and dry-run manually. Replace the
reviewer and timezone-aware review time placeholders only after reviewing the complete graph,
sources, artifact hashes, warnings, and licenses.

After every external artifact is produced, run the corresponding `record-*` command. The command
revalidates the evidence and refuses skipped or repeated stages.

## Completion gate

The final state must contain:

```text
stage=PAIR_VERIFIED
p9_oof_gate_open=true
event_count=7
supported_campaign.case_count=6
cuda_campaign.case_count=6
pair_verification.formal_case_count=12
pair_verification.provider_process_evidence_count=24
```

Then run Ruff, mypy, focused tests, and one final full pytest. Inspect one actionable GitHub Actions
run. P9 OOF may be opened only after all target-host and local gates pass. Accuracy remains unclaimed
until OOF, Holdout, and Prospective evaluation compare Hit@±1, MAE, MSE, RMSE, positional metrics,
and all required baselines.
