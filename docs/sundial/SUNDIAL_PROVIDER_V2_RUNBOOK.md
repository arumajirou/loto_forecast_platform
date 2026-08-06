# Sundial provider v2 target-host certification runbook

## Status

`HARNESS_IMPLEMENTED / FINAL_GATE_READY / TARGET_HOST_EXECUTION_PENDING`

This runbook certifies the provider-v2 implementation. It does not reuse the older
`num_samples=1` runtime evidence as proof for the new probabilistic contract.

## Preconditions

- repository branch: `feat/sundial-probabilistic-provider-v2`;
- clean worktree;
- exact expected Git commit supplied to the final gate;
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

The final gate runs Ruff, mypy, the focused Sundial tests, semantic snapshot preflight, real runtime
certification, semantic response recomputation, evidence verification, semantic ZIP-content
verification, and full repository pytest. Full pytest is mandatory and runs last.

## Request contract

`num_samples` must be integral and in the range 1 through 100. Values such as `3`, `3.0`, and
`"3"` are accepted. Fractional values such as `1.5` and `"1.5"` are rejected before inference by
both the adapter and runner.

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

## Semantic and evidence verification

The semantic verifier recomputes every distribution summary from raw samples and checks the fixed
snapshot hashes. The independent evidence verifier then recomputes SHA-256 coverage, request and
response hashes, case matrix, GPU evidence, replay classification, repository file hashes, branch,
and commit.

The semantic report is hashed and included inside the final evidence ZIP as:

```text
semantic/<RUN_ID>.json
```

A missing or symlinked `status.txt` is returned as a structured
`SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=FAIL` report with `STATUS_FILE_MISSING`.

Formal local completion requires:

```text
SUNDIAL_PROVIDER_V2_SEMANTIC_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_CERTIFICATION=PASS
SUNDIAL_PROVIDER_V2_EVIDENCE_VERIFICATION=PASS
SUNDIAL_PROVIDER_V2_FINAL_GATE=PASS
```

The PR remains Draft until these results, the full local tests, actionable CI, and substantive
review are complete.
