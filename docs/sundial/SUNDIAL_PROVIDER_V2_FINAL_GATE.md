# Sundial provider v2 final gate

## Status

`FINAL_GATE_IMPLEMENTED / TARGET_HOST_EXECUTION_PENDING`

The final gate runs all required local checks in a fixed order and stops at the first failure.
It does not replace actionable GitHub CI or substantive review.

## Mandatory order

1. Ruff on the Sundial provider, certification, verifier, and focused tests.
2. mypy on the provider and runtime scripts.
3. focused Sundial pytest files.
4. real CPU and CUDA certification with the pinned snapshot.
5. independent evidence verification and ZIP creation.
6. full repository pytest as the final heavy gate.

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
`uv`, and `nvidia-smi`. It uses `set -Eeuo pipefail`; any failed command stops the gate.

## Result

Formal local completion requires:

```text
SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS
SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_FINAL_GATE=PASS
```

Logs are written under:

```text
artifacts/sundial-provider-v2-final-gate/<GATE_ID>/
```

The evidence ZIP remains under `artifacts/sundial-provider-v2-verified/` and is accompanied by a
SHA-256 file. The PR must remain Draft until target-host results and actionable CI are reviewed.

## Focused self-test

The final-gate test verifies shell syntax, mandatory stage order, fixed identity checks, evidence
ZIP requirements, and that full pytest cannot be skipped. The dependency-light self-test result is
`3 passed`.
