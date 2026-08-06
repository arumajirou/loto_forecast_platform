# k-DPP fixed-k target-host CPU certification gate

## Status

`PARTIALLY_VERIFIED / TARGET_HOST_GATE_IMPLEMENTED / REAL_HISTORY_APPROVAL_PENDING / REAL_CPU_PAIR_EXECUTION_PENDING / PUBLIC_REGISTRATION_BLOCKED`

This phase adds an independent gate around the private runtime from PR-B. It does not include a real history bundle and does not claim that formal certification has been executed.

## Approved Train-only bundle

The gate accepts exactly:

```text
history_manifest.json
item_ids.json
training.npz
SHA256SUMS
```

The manifest must declare `VERIFIED_REAL_HISTORY`, `TRAIN_ONLY`, a read-only source, immutable raw data, verified draw order, and no future actual, Holdout, or Prospective rows. `training.npz` contains `training_indicators`, `draw_nos`, and optional `item_features`. Draw numbers must be strictly increasing and gap-free.

A separate approval JSON is required. It binds the exact manifest and checksum bytes, names the reviewer, includes a UTC review time, and requires `APPROVE-KDPP-HISTORY-BUNDLE`. Synthetic, pending, unreviewed, or changed bundles fail closed.

## Game geometry

- Numbers3 and Numbers4: one position-local lane per run, ten qualified items, `k=1`.
- MiniLoto: 31 items, `k=5`.
- Loto6: 43 items, `k=6`.
- Loto7: 37 items, `k=7`.

A shared Numbers3/4 lane remains unsupported because ordinary k-DPP sampling does not enforce one item per partition.

## Three-stage command

```bash
python scripts/run_kdpp_fixed_k_target_host.py prepare \
  --history-bundle /absolute/approved-history \
  --history-approval /absolute/history-approval.json \
  --certifier scripts/certify_kdpp_fixed_k_runtime.py \
  --workspace /absolute/evidence/kdpp-RUN_ID \
  --run-id RUN_ID \
  --source-revision COMMIT_SHA \
  --config-sha256 CONFIG_SHA256 \
  --prediction-length 1

python scripts/run_kdpp_fixed_k_target_host.py run \
  --workspace /absolute/evidence/kdpp-RUN_ID

python scripts/run_kdpp_fixed_k_target_host.py verify \
  --workspace /absolute/evidence/kdpp-RUN_ID
```

`prepare` copies and revalidates the approved bytes and binds the exact certifier hash. `run` launches the certifier twice in distinct processes with the same state inputs, seed, and request parameters. It writes external UTC prediction seals before any actuals are available. `verify` independently reopens every checksum inventory, runtime response, state, PID record, and seal.

## CPU_FORMAL requirements

`CPU_FORMAL` is emitted only when all gates pass:

- approved real Train-only history;
- immutable file and tree hashes;
- two distinct runtime PIDs;
- identical state SHA-256;
- identical prediction SHA-256;
- exact-cardinality and duplicate checks;
- finite marginals summing to `k`;
- CPU requested and effective device;
- `cpu_fallback=false`;
- null GPU fields and `gpu_not_applicable=true`;
- `actuals_used=false` and no future actuals;
- valid external UTC prediction seals;
- complete artifact inventories.

A unit fixture can make the verifier emit `CPU_FORMAL` to test orchestration. That fixture is not real-data or model-runtime certification.

## Explicit non-claims

This phase does not include or establish:

- an approved production history export;
- a real two-process target-host execution;
- public catalog or native registry registration;
- common CLI, API, TTS, or Web UI exposure;
- OOF, Holdout, or Prospective execution;
- Hit@±1, MAE, MSE, RMSE, calibration, or baseline superiority;
- Conditional Bernoulli superiority;
- GPU execution;
- merge readiness.

Public integration remains blocked until real evidence is executed, independently reviewed, and retained with its immutable hashes.
