# TabPFN-TS V2 Target-Host Runbook

Status: `IMPLEMENTED / LOCAL_FIXTURE_VERIFIED / REAL_TARGET_HOST_EXECUTION_PENDING`

This runbook executes the PR #105 runtime certifier on the target host and packages the evidence
as a self-verifying ZIP. It does not claim a real GPU pass until the generated report says
`status=PASS` and `certification_class=GPU_FORMAL`.

## Prerequisites

- checkout containing PR #97 and PR #105;
- clean, frozen root `uv.lock` environment;
- isolated provider Python with exact `tabpfn-time-series==1.2.0`, PyTorch, pandas, and NumPy;
- pinned snapshot revision
  `4972a65a1b30806315c6f92499959ffbfc69a673`;
- checkpoint `tabpfn-v2-regressor.ckpt` with the reviewed SHA-256;
- explicit acceptance of the Prior Labs checkpoint license;
- `nvidia-smi` for a formal CUDA certification.

## One-command execution

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

bash scripts/run_tabpfn_ts_v2_target_host_certification.sh \
  --repo-root "$PWD" \
  --provider-python "$PWD/environments/tabpfn-ts/.venv/bin/python" \
  --request "$PWD/configs/tabpfn_ts_campaign/v2_runtime_request.example.json" \
  --snapshot "/absolute/hf/cache/models--Prior-Labs--TabPFN-v2-reg/snapshots/4972a65a1b30806315c6f92499959ffbfc69a673" \
  --repository-cache-root "/absolute/hf/cache/models--Prior-Labs--TabPFN-v2-reg" \
  --device cuda \
  --accept-prior-labs-license
```

The example request is a structural smoke input. Replace it with an immutable request built from the
intended historical Loto7 data before using the artifact as formal project evidence.

## Automated gates

The wrapper fails before certification when required commands, paths, or provider imports are
missing. The certifier then verifies checkpoint provenance before child-process execution and
requires two distinct, deterministic provider runs. The packager rejects incomplete reports,
CPU fallback, non-finite or non-37 outputs, missing GPU PID/UUID/VRAM evidence, mismatched prediction
hashes, tampered source files, and files not covered by the run `SHA256SUMS`.

## Outputs

- `artifacts/tabpfn-ts-v2-runtime/<RUN_ID>/runtime-certification-report.json`;
- per-process request, response, stdout, and stderr files;
- run-level `SHA256SUMS`;
- bootstrap console log, host inventory, and status file;
- `artifacts/tabpfn-ts-v2-runtime-bundles/<RUN_ID>-evidence.zip`;
- adjacent ZIP `.sha256` file.

The ZIP contains `README.md`, `VERIFICATION_REPORT.md`, `RUNBOOK.md`,
`ARTIFACT_MANIFEST.json`, package-level `SHA256SUMS`, host inventory, and the complete runtime
evidence directory.

## Interpretation

`CPU_SMOKE` proves orchestration only. `GPU_FORMAL` proves the configured runtime evidence gates for
that exact checkpoint, host, request, seed, and code revision. Neither result proves Hit@±1,
MAE/MSE/RMSE, Holdout or Prospective performance, or superiority over any baseline.
