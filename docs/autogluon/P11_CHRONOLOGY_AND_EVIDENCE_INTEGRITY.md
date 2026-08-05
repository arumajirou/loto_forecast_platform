# AutoGluon P11 Chronology and Evidence Integrity

Status: `IMPLEMENTED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_PENDING`

## Purpose

P11 layers strict chronological preflight and guarded evidence finalization on top of the
P10 provider and certification harness. It does not claim real AutoGluon execution, CI
success, GPU use, or accuracy improvement.

## Strict provider preflight

Schema-v2 execution now routes through `run_provider_v2_strict`, which rejects requests
before model import, fit, or load when any of these conditions are present:

- source-order values are not integers;
- source order is not strictly increasing;
- source timestamps are not ISO-8601 compatible;
- source timestamps are not strictly increasing;
- predictor frequency differs from the synthetic timeline frequency;
- a custom target column is requested before explicit target-column mapping exists.

Rows are never sorted, deduplicated, interpolated, or repaired automatically. Schema-v1
continues to use the explicit legacy compatibility path.

## Guarded runtime-certification finalization

The P11 guarded CLI runs the existing P10 harness and then rewrites its final report and
portable hash manifest using stricter rules:

- any unexpected scenario failure makes the complete campaign `FAILED`;
- `PARTIALLY_VERIFIED` is reserved for verified plus runtime-blocked scenarios only;
- symbolic links and special files are recorded as evidence-tree violations;
- only regular files are included in `SHA256SUMS`;
- absolute paths, parent traversal, duplicate entries, missing files, unlisted files, and
  content-hash mismatches are rejected;
- the report's canonical `report_sha256` is independently recomputed;
- each guard pass receives a UTC-microsecond/PID verification ID.

Run the guarded campaign:

```bash
PYTHONPATH=src uv run python -m loto.autogluon_campaign.runtime_certification_guarded \
  --repo-root "$PWD" \
  --output-dir artifacts/autogluon/runtime-certification/<run-id>
```

Verify an existing output without executing AutoGluon:

```bash
PYTHONPATH=src uv run python -m loto.autogluon_campaign.runtime_certification_guarded \
  --verify-output artifacts/autogluon/runtime-certification/<run-id>
```

## Local verification

- AutoGluon focused and regression tests: 51 passed;
- Python compileall: PASS;
- Python source lines over 100 characters: 0;
- Ruff: unavailable in the execution environment;
- real AutoGluon 1.5.0 runtime: not executed;
- GitHub Actions: blocked before workflow step creation.
