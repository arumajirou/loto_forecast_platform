# TSFM Runtime Certification Progress

Updated: 2026-08-01

## Current Status

- Total models: 21
- Runtime certified: 8
- Blocked: 11
- Pending: 2
- Formal certification progress: 38.1%
- Judged progress: 90.5%
- Current branch: feat/timesfm-2-5-transformers-runtime-audit-v1
- Next model: toto-2.0-4m
## Certified

### chronos-2

- Branch: feat/chronos-2-runtime-audit-v1
- Commit: 8ee8146
- Push: origin/feat/chronos-2-runtime-audit-v1
- repo_id: amazon/chronos-2
- revision: 29ec3766d36d6f73f0696f85560a422f50e8498c
- runner: scripts/run_chronos_2_provider.py
- provider: src/loto/models/providers/chronos.py
- GPU: cuda:0
- CPU fallback: false
- CPU preprocessing: true
- peak VRAM: 497113088
- external PID captures: 11
- GPU PID: 919682
- weight SHA-256: ddcda3c7508bf2528087723e98a20707cc04b7f370ae275a9fd88078ddba4f42
- config SHA-256: ef1143bfdc9c0376d9a056eefca46cb4b1ec3d0ffacd541ff56feb40fb708031
- license: Apache-2.0, APPROVED
- dedicated test: tests/test_chronos_2_runtime_audit.py
- hash verification: audit/tsfm-runtime/chronos-2/sha256sum.txt OK

## Remaining Ledger Order

1. t0-alpha
2. toto-2.0-4m
3. toto-open-base

## Blocked

### chronos-t5-base

- Branch: feat/chronos-t5-base-runtime-audit-v1
- Commit: acf69da
- Push: origin/feat/chronos-t5-base-runtime-audit-v1
- repo_id: amazon/chronos-t5-base
- revision: ad294eaacead15db499b740ea4122266dd2a81a2
- status: BLOCKED
- blocked reason: MODEL_WEIGHTS_MISSING
- checked snapshot: /mnt/e/env/huggingface/hub/models--amazon--chronos-t5-base/snapshots/ad294eaacead15db499b740ea4122266dd2a81a2
- runtime executed: false
- CPU fallback: false
- license: apache-2.0 from ledger, review BLOCKED until local pinned model card or license files are inspected
- dedicated test: tests/test_chronos_t5_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/chronos-t5-base/sha256sum.txt OK
- resume condition: provide the pinned local snapshot with model.safetensors, config.json, and generation_config.json, then rerun CUDA runtime certification with external PID sampling.

### granite-flowstate-r1

- Branch: feat/granite-flowstate-r1-runtime-audit-v1
- Commit: 2a4dc3e
- Push: origin/feat/granite-flowstate-r1-runtime-audit-v1
- repo_id: ibm-granite/granite-timeseries-flowstate-r1
- revision: 05effc6cb39ee16dce9dd0064ed1a76e4b8ff464
- status: BLOCKED
- blocked reason: FIXED_SNAPSHOT_MISSING
- checked snapshot: /mnt/e/env/huggingface/hub/models--ibm-granite--granite-timeseries-flowstate-r1/snapshots/05effc6cb39ee16dce9dd0064ed1a76e4b8ff464
- candidate loose files: /mnt/e/env/ts/loto_platform_unified/runtime/tsfm_lab/models/ibm-granite__granite-timeseries-flowstate-r1
- runtime executed: false
- CPU fallback: false
- license: apache-2.0 from ledger, review BLOCKED until pinned snapshot license/model card is inspected
- dedicated test: tests/test_granite_flowstate_r1_runtime_audit.py
- hash verification: audit/tsfm-runtime/granite-flowstate-r1/sha256sum.txt OK
- resume condition: materialize the pinned HF snapshot, verify SHA-256 values, implement/select the FlowState runtime API, and rerun CUDA runtime certification with external PID sampling.

### kronos-base

- Branch: feat/kronos-base-runtime-audit-v1
- Commit: 0e13c2f
- Push: origin/feat/kronos-base-runtime-audit-v1
- repo_id: NeoQuasar/Kronos-base
- revision: 2b554741eca47781b64468546e77fef3e85130e6
- status: BLOCKED
- blocked reason: PARTIAL_SNAPSHOT
- checked snapshot: /mnt/e/env/huggingface/hub/models--NeoQuasar--Kronos-base/snapshots/2b554741eca47781b64468546e77fef3e85130e6
- snapshot finding: snapshot exists and revision matches, but only README.md is present
- missing files: config.json, model.safetensors
- runtime executed: false
- CPU fallback: false
- license: MIT from pinned snapshot README metadata, APPROVED
- dedicated test: tests/test_kronos_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/kronos-base/sha256sum.txt OK
- resume condition: install the exact pinned revision into the configured local Hugging Face cache with config.json and model.safetensors present, then rerun CUDA runtime certification with external PID sampling.

### lag-llama

- Branch: feat/lag-llama-runtime-audit-v1
- Commit: a9edfd8
- Push: origin/feat/lag-llama-runtime-audit-v1
- repo_id: time-series-foundation-models/Lag-Llama
- revision: 72dcfc29da106acfe38250a60f4ae29d1e56a3d9
- status: BLOCKED
- blocked reason: PARTIAL_SNAPSHOT
- checked snapshot: /mnt/e/env/huggingface/hub/models--time-series-foundation-models--Lag-Llama/snapshots/72dcfc29da106acfe38250a60f4ae29d1e56a3d9
- snapshot finding: snapshot exists and revision matches, but only README.md is present
- missing files: model checkpoint (*.ckpt or *.safetensors)
- runtime executed: false
- CPU fallback: false
- license: Apache-2.0 from pinned snapshot README metadata, APPROVED
- dedicated test: tests/test_lag_llama_runtime_audit.py
- hash verification: audit/tsfm-runtime/lag-llama/sha256sum.txt OK
- resume condition: install the exact pinned revision into the configured local Hugging Face cache with the Lag-Llama checkpoint file present, then rerun CUDA runtime certification with external PID sampling.

### moirai-1.0-base

- Branch: feat/moirai-1-0-base-runtime-audit-v1
- Commit: e30dfbc
- Push: origin/feat/moirai-1-0-base-runtime-audit-v1
- repo_id: Salesforce/moirai-1.0-R-base
- revision: 4fa939a8800d9da346c0280f3d9aeba0d2d35877
- status: BLOCKED
- blocked reason: LICENSE_REVIEW_REQUIRED
- checked snapshot: /mnt/e/env/huggingface/hub/models--Salesforce--moirai-1.0-R-base/snapshots/4fa939a8800d9da346c0280f3d9aeba0d2d35877
- snapshot finding: snapshot exists and revision matches, but only README.md is present
- license: CC-BY-NC-4.0, REJECTED for commercial runtime certification
- runtime executed: false
- CPU fallback: false
- dedicated test: tests/test_moirai_1_0_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/moirai-1.0-base/sha256sum.txt OK
- resume condition: use only if policy permits CC-BY-NC-4.0 non-commercial models; otherwise choose a commercially usable Moirai revision/model. A complete pinned snapshot with weights is also required before runtime probing.

### moirai-2.0-small

- Branch: feat/moirai-2-0-small-runtime-audit-v1
- Commit: e4be0a6
- Push: origin/feat/moirai-2-0-small-runtime-audit-v1
- repo_id: Salesforce/moirai-2.0-R-small
- revision: 30f43ff08c8494f4943ae1521e9d4e94a0fbb389
- status: BLOCKED
- blocked reason: LICENSE_REVIEW_REQUIRED
- checked snapshot: /mnt/e/env/huggingface/hub/models--Salesforce--moirai-2.0-R-small/snapshots/30f43ff08c8494f4943ae1521e9d4e94a0fbb389
- snapshot finding: snapshot exists with config.json and model.safetensors
- weight SHA-256: fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669
- config SHA-256: 6b74b03c8ec199fabc352c0203465958142ca468183da68549652734836f853d
- license: CC-BY-NC-4.0, REJECTED for commercial runtime certification
- runtime executed: false
- CPU fallback: false
- dedicated test: tests/test_moirai_2_0_small_runtime_audit.py
- hash verification: audit/tsfm-runtime/moirai-2.0-small/sha256sum.txt OK
- resume condition: use only if policy permits CC-BY-NC-4.0 non-commercial models; otherwise choose a commercially usable Moirai model. Runtime probing can resume only after license approval.

### moment-1-large

- Branch: feat/moment-1-large-runtime-audit-v1
- Commit: 6a6a910
- Push: origin/feat/moment-1-large-runtime-audit-v1
- repo_id: AutonLab/MOMENT-1-large
- revision: ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc
- status: BLOCKED
- blocked reason: PARTIAL_SNAPSHOT
- checked snapshot: /mnt/e/env/huggingface/hub/models--AutonLab--MOMENT-1-large/snapshots/ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc
- snapshot finding: snapshot exists and revision matches, but only README.md is present
- missing files: config.json, model weight file
- runtime executed: false
- CPU fallback: false
- license: MIT from pinned snapshot README metadata, APPROVED
- dedicated test: tests/test_moment_1_large_runtime_audit.py
- hash verification: audit/tsfm-runtime/moment-1-large/sha256sum.txt OK
- resume condition: Install the exact pinned revision into the configured local Hugging Face cache with config.json and model weight files present.

### moment-1-small

- Branch: feat/moment-1-small-runtime-audit-v1
- Commit: 224a526
- Push: origin/feat/moment-1-small-runtime-audit-v1
- repo_id: AutonLab/MOMENT-1-small
- revision: 411e288267f82cce86296dbe4d6c8bc533cc162f
- status: BLOCKED
- blocked reason: FIXED_SNAPSHOT_MISSING
- checked snapshot: /mnt/e/env/huggingface/hub/models--AutonLab--MOMENT-1-small/snapshots/411e288267f82cce86296dbe4d6c8bc533cc162f
- snapshot finding: repo cache missing
- runtime executed: false
- CPU fallback: false
- license: MIT from ledger, review BLOCKED until pinned snapshot/model card is available
- dedicated test: tests/test_moment_1_small_runtime_audit.py
- hash verification: audit/tsfm-runtime/moment-1-small/sha256sum.txt OK
- resume condition: Install the exact pinned revision into the configured local Hugging Face cache, including model card/license metadata, config, and model weight files.

### sundial-base

- Branch: feat/sundial-base-runtime-audit-v1
- Commit: 276b436
- Push: origin/feat/sundial-base-runtime-audit-v1
- repo_id: thuml/sundial-base-128m
- revision: 3212e42564493f520593e5414af4367fc4b49226
- status: BLOCKED
- blocked reason: TRUST_REMOTE_CODE_REVIEW_REQUIRED
- checked snapshot: /mnt/e/env/huggingface/hub/models--thuml--sundial-base-128m/snapshots/3212e42564493f520593e5414af4367fc4b49226
- snapshot finding: complete snapshot with custom Python remote-code files
- weight SHA-256: 414435b508391f92afadd2aaeec418c806776aeccbce12e638d73a139ca5ca78
- config SHA-256: 173dd40c0a7e08a71b660110fd6334ee85eb9f6ce6f30df0a6cbaea3bb1ff3b4
- runtime executed: false
- CPU fallback: false
- license: Apache-2.0 APPROVED
- dedicated test: tests/test_sundial_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/sundial-base/sha256sum.txt OK
- resume condition: Complete and approve a security review of the pinned remote-code files before running CUDA runtime certification.

### t0-alpha

- Branch: feat/t0-alpha-runtime-audit-v1
- Commit: 49071bf
- Push: origin/feat/t0-alpha-runtime-audit-v1
- repo_id: theforecastingcompany/t0-alpha
- revision: f8727c2357e0d81f1d9f56fe3aaac43068b5fc72
- status: BLOCKED
- blocked reason: GATED_ACCESS_REQUIRED
- checked snapshot: /mnt/e/env/huggingface/hub/models--theforecastingcompany--t0-alpha/snapshots/f8727c2357e0d81f1d9f56fe3aaac43068b5fc72
- runtime executed: false
- CPU fallback: false
- license: Apache-2.0 from pinned snapshot README metadata.
- dedicated test: tests/test_t0_alpha_runtime_audit.py
- hash verification: audit/tsfm-runtime/t0-alpha/sha256sum.txt OK
- resume condition: Accept/verify gated model access and install the exact pinned revision into the configured local Hugging Face cache with config.json and model weights.

### timesfm-2.5-transformers

- Branch: feat/timesfm-2-5-transformers-runtime-audit-v1
- Commit: pending
- Push: pending
- repo_id: google/timesfm-2.5-200m-transformers
- revision: 5a9806b9b291fad9233b5249d88263f1846304d3
- status: BLOCKED
- blocked reason: FIXED_SNAPSHOT_MISSING
- checked snapshot: /mnt/e/env/huggingface/hub/models--google--timesfm-2.5-200m-transformers/snapshots/5a9806b9b291fad9233b5249d88263f1846304d3
- runtime executed: false
- CPU fallback: false
- license: Apache-2.0 from ledger; pinned local model card/license files are unavailable.
- dedicated test: tests/test_timesfm_2_5_transformers_runtime_audit.py
- hash verification: audit/tsfm-runtime/timesfm-2.5-transformers/sha256sum.txt OK
- resume condition: Install the exact pinned Transformers revision into the configured local Hugging Face cache with config.json and model.safetensors present.
