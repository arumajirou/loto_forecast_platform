# Runbook

## Validate a policy artifact

```bash
PYTHONPATH=src python scripts/run_provider_sandbox.py validate-policy \
  --policy configs/provider_sandbox/default_policy.json
```

Use `--check-host-paths` only after replacing example source paths with reviewed real paths.

## Build an argv plan

```bash
PYTHONPATH=src python scripts/run_provider_sandbox.py plan \
  --policy /absolute/policy.json \
  --request /absolute/request.json \
  --backend-evidence /absolute/backend.json > plan.json
```

Review the complete argv tuple. Do not copy it into a shell string.

## Verify effective evidence

```bash
PYTHONPATH=src python scripts/run_provider_sandbox.py verify-effective \
  --policy /absolute/policy.json \
  --request /absolute/request.json \
  --effective /absolute/effective.json
```

Exit `0` means every required field matched. Exit `1` means mismatch or incomplete evidence. Exit `2`
means malformed input or an operational error.

## Verify a retained bundle

```bash
PYTHONPATH=src python scripts/run_provider_sandbox.py verify-bundle \
  --bundle /absolute/evidence-directory
```

Do not treat fixture evidence or a `VERIFIED` structural comparison as kernel security certification.
