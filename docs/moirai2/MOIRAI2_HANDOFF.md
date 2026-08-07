# Moirai 2.0 Handoff

PR #83 is the P0-P6 base, PR #86 is P7, PR #87 is the P8 certifier, and P8A continues only on
`feat/moirai2-runtime-campaign-v1`. Do not retarget or write to any parent branch.

On the target host, first generate the isolated lane lockfile manually and review the resulting
diff. Do not represent lock generation alone as success. After approval, run the fail-closed
preflight with a new output directory:

```bash
uv run python scripts/preflight_moirai2_runtime_lane.py \
  --runtime-lane supported-py311 \
  --device cpu \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --output-dir artifacts/moirai2/preflight/<RUN_ID>
```

Then run the full six-case campaign:

```bash
uv run python scripts/run_moirai2_runtime_campaign.py \
  --campaign-id <RUN_ID> \
  --runtime-lane supported-py311 \
  --device cpu \
  --snapshot-path /absolute/path/to/pinned/snapshot \
  --output-dir artifacts/moirai2/runtime-campaign/<RUN_ID>
```

Repeat with `cuda13-experimental` and `--device cuda` only after the CPU lane is understood. Never
reuse an output directory. Cases run serially by design. Preserve `campaign_summary.json`, every
case request and response, GPU samples, stdout/stderr, exit codes, manifests, and `SHA256SUMS`.

Do not open OOF, Holdout, or Prospective work until all six real cases pass and
`formal_runtime_certified=true`. Keep all stacked PRs Draft until real execution, Ruff, mypy,
focused tests, one final full pytest, and one actionable CI run pass.
