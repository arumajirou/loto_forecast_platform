# Darts runtime bootstrap

The runtime bootstrap is the only supported transition from an isolated project manifest
to a campaign-approved Darts runtime. It does not train or predict.

## Ordered stages

1. Validate repository-relative paths and the selected project `pyproject.toml`.
2. Resolve the `uv` executable.
3. Run `uv lock --project <project> --python 3.13`.
4. Hash the generated non-empty `uv.lock`.
5. Run `uv sync --project <project> --frozen --python 3.13`.
6. Run the existing runtime preflight through `uv run --project ... --frozen`.
7. Verify the preflight JSON SHA-256 and its observed lockfile SHA-256.
8. Create `CAMPAIGN_APPROVAL.json` only when every required stage is `PASS`.

## Fail-closed behavior

A stale preflight report, bootstrap report, or approval file is deleted before execution.
Missing tools, lock resolution failures, sync failures, missing CUDA, or unavailable required
packages return `BLOCKED`. Invalid reports, hash mismatches, exit-code mismatches, or contract
violations return `FAIL`. Neither outcome creates an approval file.

## Evidence

Command output is not copied into the report. The report retains command identity, return
code, byte counts, and SHA-256 values for stdout and stderr. It also stores lockfile hashes,
the preflight report hash, process ID, and a tamper-sensitive bootstrap report hash.

The approval file binds the exact lockfile, preflight report, and bootstrap report hashes.
Changing any of those invalidates campaign permission.

## Commands

```bash
uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_notorch.yaml \
  --repository-root .

uv run python scripts/run_darts_runtime_bootstrap.py \
  --profile configs/darts_campaign/runtime_bootstrap_torch.yaml \
  --repository-root .
```

A real campaign may start only when the selected profile creates a valid
`CAMPAIGN_APPROVAL.json` with `campaign_execution_allowed: true`.
