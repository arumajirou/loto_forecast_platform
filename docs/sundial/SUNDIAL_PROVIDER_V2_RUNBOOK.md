# Sundial provider v2 target-host certification runbook

## Status

`HARNESS_IMPLEMENTED / FINAL_GATE_READY / TARGET_HOST_EXECUTION_PENDING`

This runbook certifies the provider-v2 implementation. It does not reuse the older
`num_samples=1` runtime evidence as proof for the new probabilistic contract.

## Preconditions

- repository branch: `feat/sundial-probabilistic-provider-v2`;
- clean or intentionally recorded worktree;
- pinned snapshot directory ending in
  `3212e42564493f520593e5414af4367fc4b49226`;
- `environments/sundial/uv.lock` present;
- `uv` and `nvidia-smi` available;
- NVIDIA GPU visible to the current user.

## Recommended final-gate command

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

The final gate runs Ruff, mypy, focused Sundial tests, real runtime certification, independent
evidence verification, and full repository pytest. Full pytest is mandatory and runs last.

## Certification-only command

```bash
bash scripts/run_sundial_provider_v2_certification.sh \
  /mnt/e/env/ts/loto_forecast_platform \
  "$SNAPSHOT"
```

## Certification matrix

```text
cpu-smoke-ns001
cuda-ns001
cuda-ns003
cuda-ns020
cuda-ns050
cuda-ns100
cuda-replay-a
cuda-replay-b
```

Each CUDA case must prove internal and external GPU PID and VRAM observations, finite sample and
point values, exact sample shape, and no CPU fallback. Replay must be `EXACT` or `NUMERIC_CLOSE`.

## Evidence verification

The independent verifier recomputes SHA-256 coverage, request and response hashes, case matrix,
GPU evidence, replay classification, repository file hashes, branch, and commit. Only verifier PASS
creates the shareable evidence ZIP.

Formal local completion requires:

```text
SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS
SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_FINAL_GATE=PASS
```

The PR remains Draft until these results, full local tests, actionable CI, and review are complete.
