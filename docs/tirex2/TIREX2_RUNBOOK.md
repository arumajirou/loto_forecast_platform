# TiRex-2 runbook

Use the dedicated Python 3.12 environment. Set `HF_HOME` or `HF_HUB_CACHE` to the trusted cache
root containing the pinned snapshot. The runner accepts `--request` and `--response`; output is
written atomically. A CUDA request fails when CUDA is unavailable instead of falling back.

Do not enable network model resolution: `local_files_only=true` is mandatory. Do not treat the
reference manifest as model serialization. Preserve request, response, environment lock hash,
model hashes, logs, process evidence, and exit code for each run ID.

Run the reload gate with `python -m loto.tirex2_campaign.runtime_certification` and explicit
`--request`, `--output-root`, and `--provider-script` arguments. A provider or certification
failure returns a non-zero process exit code after preserving structured JSON evidence.

## Reviewed lock gate

Generate a candidate without changing the runtime lane:

```bash
uv run python scripts/generate_tirex2_lock_candidate.py \
  --output-root artifacts/tirex2-lock-candidates
```

Review `LOCK_REVIEW_REPORT.json`, then perform a dry-run with the exact candidate lock SHA-256:

```bash
uv run python scripts/install_reviewed_tirex2_lock.py \
  --candidate /absolute/path/to/candidate \
  --reviewer REVIEWER_ID \
  --reviewed-at 2026-08-06T08:41:00+09:00 \
  --expected-candidate-lock-sha256 LOCK_SHA256
```

Apply only after review by adding both `--apply` and
`--approval-token APPLY-REVIEWED-TIREX2-LOCK`. Validate the installed three-artifact set before
runtime startup:

```bash
uv run python scripts/preflight_tirex2_runtime_lane.py \
  --output artifacts/tirex2-runtime-preflight.json
```

The provider itself repeats the reviewed-lock validation before importing `tirex2`.
