# Sundial provider v2 final gate

## Status

`FINAL_GATE_IMPLEMENTED / REMAINING_HARDENING_WIRED / TARGET_HOST_EXECUTION_PENDING`

The final gate runs all required local checks in a fixed order and stops at the first failure.
It does not replace actionable GitHub CI or substantive review.

## Mandatory order

1. Ruff on the Sundial provider, certification, semantic verifier, evidence verifier, and tests.
2. mypy on the provider and runtime scripts.
3. focused Sundial pytest files, including remaining-hardening coverage.
4. semantic preflight of the pinned snapshot before model loading.
5. real CPU and CUDA certification with the pinned snapshot.
6. independent semantic recomputation over all eight runtime responses.
7. independent evidence verification and ZIP creation with the semantic report embedded.
8. archive-content verification for `semantic/<RUN_ID>.json`.
9. full repository pytest as the final heavy gate.

Full pytest cannot be disabled. A skipped stage cannot produce final-gate PASS.

## Command

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1
set -Eeuo pipefail

EXPECTED_COMMIT="$(git rev-parse HEAD)"
SNAPSHOT_ROOT="/mnt/e/env/huggingface/hub/models--thuml--sundial-base-128m/snapshots"
SNAPSHOT="$SNAPSHOT_ROOT/3212e42564493f520593e5414af4367fc4b49226"

bash scripts/run_sundial_provider_v2_final_gate.sh \
  /mnt/e/env/ts/loto_forecast_platform \
  "$SNAPSHOT" \
  "$EXPECTED_COMMIT"
```

The script requires a clean worktree, the expected branch, the exact commit, the pinned snapshot,
`uv`, and `nvidia-smi`. It exports `UV_FROZEN=1`, uses `uv run --frozen`, and stops on any failed
command through `set -Eeuo pipefail`.

## Result

Formal local completion requires:

```text
SUNDIAL_PROVIDER_V2_SEMANTIC_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS
SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_FINAL_GATE=PASS
```

Logs are written under:

```text
artifacts/sundial-provider-v2-final-gate/<GATE_ID>/
```

The evidence ZIP remains under `artifacts/sundial-provider-v2-verified/`, is accompanied by a
SHA-256 file, and must contain the semantic verification JSON. The PR must remain Draft until
target-host results and actionable CI are reviewed.

## Focused hardening coverage

The focused set covers:

- strict rejection of fractional or non-integer `num_samples` in both runner and adapter;
- acceptance of integral representations within the supported range;
- structured `STATUS_FILE_MISSING` verification failure;
- semantic report embedding and ZIP SHA-256 generation;
- final-gate and package-gate semantic wiring;
- shell syntax, fixed stage order, fixed identity, and full-pytest non-skippability.

These tests are wired into the target-host focused gate. Real target-checkout execution remains
pending.
