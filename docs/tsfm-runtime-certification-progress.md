# TSFM Runtime Certification Progress

Updated: 2026-08-01

## Current Status

- Total models: 21
- Runtime certified: 17 / 21
- Blocked: 4 / 21
- Pending: 0 / 21
- Formal certification progress: 81.0%
- Judged progress: 100.0%
- Current branch: feat/toto-open-base-runtime-audit-v1
- Next model: NO_PENDING_MODELS
## Certified

### moirai-2.0-small

- repo_id: Salesforce/moirai-2.0-R-small
- revision: 30f43ff08c8494f4943ae1521e9d4e94a0fbb389
- status: CERTIFIED
- runtime certification scope: FULL_INFERENCE
- license scope: PERSONAL_NONCOMMERCIAL_ONLY
- commercial deployment certified: false
- native forecast contract used: true
- lottery domain compatibility certified: false
- forecast accuracy certified: false
- prediction shape: [7]
- output finite: true
- model device: cuda:0
- CPU fallback: false
- peak VRAM: 80993280 bytes
- external runtime PID: 693777
- external PID captures: 13
- external maximum GPU memory: 372.0 MiB
- model parameters: 11387208
- context length: 128
- prediction length: 1
- target dimension: 7
- uni2ts: 2.0.0
- GluonTS: 0.14.4
- Torch: 2.13.0+cu130
- license: CC-BY-NC-4.0
- license review: APPROVED_PERSONAL_NONCOMMERCIAL
- personal non-commercial use: true
- commercial use: false
- hash verification: audit/tsfm-runtime/moirai-2.0-small/sha256sum.txt OK


### toto-2.0-4m

- repo_id: Datadog/Toto-2.0-4m
- revision: 8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9
- code revision: 44ea4e88852228039564aa3e76fac26aafac0803
- status: CERTIFIED
- runtime certification scope: FULL_INFERENCE
- probabilistic forecast executed: true
- native domain contract used: true
- lottery domain compatibility certified: false
- forecast accuracy certified: false
- input shape: [1, 7, 512]
- output shape: [9, 1, 7, 1]
- output finite: true
- model device: cuda:0
- output device: cuda:0
- CPU fallback: false
- peak VRAM: 66428928 bytes
- external runtime PID: 644605
- external PID captures: 19
- external maximum GPU memory: 358.0 MiB
- model parameters: 4144448
- Python: 3.12.13
- toto-models: 1.0.0
- toto-2: 2.0.0
- license: Apache-2.0, APPROVED
- hash verification: audit/tsfm-runtime/toto-2.0-4m/sha256sum.txt OK


### kronos-base

- repo_id: NeoQuasar/Kronos-base
- revision: 2b554741eca47781b64468546e77fef3e85130e6
- tokenizer repo_id: NeoQuasar/Kronos-Tokenizer-base
- tokenizer revision: 0e0117387f39004a9016484a186a908917e22426
- code revision: 67b630e67f6a18c9e9be918d9b4337c960db1e9a
- status: CERTIFIED
- runtime certification scope: FULL_INFERENCE
- native domain: financial OHLCV / K-line
- tokenizer executed: true
- autoregressive forecast executed: true
- native domain contract used: true
- lottery domain compatibility certified: false
- forecast accuracy certified: false
- prediction shape: [4, 6]
- prediction columns: ['open', 'high', 'low', 'close', 'volume', 'amount']
- output finite: true
- model device: cuda:0
- tokenizer device: cuda:0
- CPU fallback: false
- peak VRAM: 473748992 bytes
- external runtime PID: 598858
- external PID captures: 9
- external maximum GPU memory: 758.0 MiB
- model parameters: 102310592
- tokenizer parameters: 3958042
- license: MIT, APPROVED
- dedicated test: tests/test_kronos_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/kronos-base/sha256sum.txt OK


### granite-flowstate-r1

- repo_id: ibm-granite/granite-timeseries-flowstate-r1
- revision: 05effc6cb39ee16dce9dd0064ed1a76e4b8ff464
- status: CERTIFIED
- runtime certification scope: FULL_INFERENCE
- forecast head executed: true
- forecast accuracy certified: false
- model class: FlowStateForPrediction
- output class: FlowStateForPredictionOutput
- parameter count: 9069312
- context length: 2048
- prediction length: 24
- certification prediction shape: [7, 1, 1]
- mean prediction shape: [7, 24, 1]
- quantile prediction shape: [7, 9, 24, 1]
- output finite: true
- model device: cuda:0
- input device: cuda:0
- mean output device: cuda:0
- quantile output device: cuda:0
- CPU fallback: false
- peak VRAM: 824376832 bytes
- external runtime PID: 548753
- external PID captures: 9
- external maximum GPU memory: 1180.0 MiB
- config SHA-256: ba2cfa7a3cfb6f0137e3c39bc855dbd4fa7a6a035136960b256e558a13902dc8
- model.safetensors SHA-256: 07a7844db841047d3a99ce9c6ce0ce5139a24d1f42e919c37c2d1e285fa0ff98
- model.sig SHA-256: 6ae2b1c2144889f57d3c499fe4dc93e4c4320b14d1211828664adb4ed4a55f0e
- license: Apache-2.0, APPROVED
- dedicated test: tests/test_granite_flowstate_r1_runtime_audit.py
- hash verification: audit/tsfm-runtime/granite-flowstate-r1/sha256sum.txt OK


### timesfm-2.5-transformers

- repo_id: google/timesfm-2.5-200m-transformers
- revision: 5a9806b9b291fad9233b5249d88263f1846304d3
- status: CERTIFIED
- runtime certification scope: FULL_INFERENCE
- forecast head executed: true
- forecast accuracy certified: false
- model class: TimesFm2_5ModelForPrediction
- output class: TimesFm2_5OutputForPrediction
- context length: 512
- native prediction length: 128
- certification prediction length: 1
- point prediction shape: [7, 1]
- full prediction shape: [7, 1, 10]
- native mean shape: [7, 128]
- native full shape: [7, 128, 10]
- output finite: true
- model device: cuda:0
- input devices: ['cuda:0']
- mean output device: cuda:0
- full output device: cuda:0
- CPU fallback: false
- peak VRAM: 1642211328 bytes
- external runtime PID: 489233
- external PID captures: 9
- external maximum GPU memory: 2002.0 MiB
- config SHA-256: 452ecae918f67b2e7d0f2892ab424d1876939e70d077db3708a4fe8ca03a7de5
- model.safetensors SHA-256: b53f6d52114e2ad786890f3c4637ce05f580b7800d6e24401f88b398b76035ef
- license: Apache-2.0, APPROVED
- dedicated test: tests/test_timesfm_2_5_transformers_runtime_audit.py
- hash verification: audit/tsfm-runtime/timesfm-2.5-transformers/sha256sum.txt OK


### moment-1-large

- repo_id: AutonLab/MOMENT-1-large
- revision: ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc
- status: CERTIFIED
- runtime certification scope: EXECUTION_ONLY
- runtime executed: true
- pipeline class: MOMENTPipeline
- output class: TimeseriesOutputs
- context length: 512
- prediction length: 1
- prediction shape: [7, 1, 1]
- output finite: true
- model device: cuda:0
- input device: cuda:0
- output device: cuda:0
- CPU fallback: false
- peak VRAM: 1525199360 bytes
- external runtime PID: 450256
- external PID captures: 13
- external maximum GPU memory: 1746.0 MiB
- forecast head: FINE_TUNING_REQUIRED
- forecast head pretrained: false
- forecast accuracy certified: false
- config SHA-256: b0111650e8718e31d7e89575666aa3e140747d35279ec1a7c9f6ed7616c29433
- model.safetensors SHA-256: a56928052ac6f5d09b97c3834bea6ce3aef9f02b513b5fac98954e7377801572
- license: MIT, APPROVED
- dedicated test: tests/test_moment_1_large_runtime_audit.py
- hash verification: audit/tsfm-runtime/moment-1-large/sha256sum.txt OK


### moment-1-small

- repo_id: AutonLab/MOMENT-1-small
- revision: 411e288267f82cce86296dbe4d6c8bc533cc162f
- status: CERTIFIED
- runtime certification scope: EXECUTION_ONLY
- runtime executed: true
- pipeline class: MOMENTPipeline
- output class: TimeseriesOutputs
- context length: 512
- prediction length: 1
- prediction shape: [7, 1, 1]
- output finite: true
- model device: cuda:0
- input device: cuda:0
- output device: cuda:0
- CPU fallback: false
- peak VRAM: 197549568 bytes
- external runtime PID: 426259
- external PID captures: 4
- external maximum GPU memory: 498.0 MiB
- forecast head: FINE_TUNING_REQUIRED
- forecast head pretrained: false
- forecast accuracy certified: false
- config SHA-256: 6456b8e6f017323e8ef372c338c993380e246cb6291ffb8ca21fe7dfc53d0a6f
- model.safetensors SHA-256: 785e6c6f57ffa7cac7e2a1fff6369618d49f2f441563ddea76c866231e5aa877
- license: MIT, APPROVED
- dedicated test: tests/test_moment_1_small_runtime_audit.py
- hash verification: audit/tsfm-runtime/moment-1-small/sha256sum.txt OK


### chronos-t5-base

- repo_id: amazon/chronos-t5-base
- revision: ad294eaacead15db499b740ea4122266dd2a81a2
- status: CERTIFIED
- runtime executed: true
- pipeline class: ChronosPipeline
- model class: ChronosModel
- prediction shape: [7]
- quantile shape: [7, 1, 9]
- mean shape: [7, 1]
- output finite: true
- model device: cuda:0
- input device: cpu
- tokenizer device: cpu
- CPU preprocessing: true
- CPU fallback: false
- peak VRAM: 1606348800 bytes
- external runtime PID: 402016
- external PID captures: 11
- external maximum GPU memory: 1876.0 MiB
- weight SHA-256: 44a2eef44aa13d9048a625ea289beb1ea5d709d7b2044f72134c974132644bf2
- config SHA-256: 20a32a40aa31ec99387b5b68f272ec49cbcfec61cfefafbd32ed81dfe474c243
- generation config SHA-256: 8f6833851ce53496a43ef87a975c766f7a3049e2d598ecef609a526ca6308534
- license: Apache-2.0, APPROVED
- dedicated test: tests/test_chronos_t5_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/chronos-t5-base/sha256sum.txt OK


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

No pending models remain.

## Blocked


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


### sundial-base

- Branch: feat/sundial-base-runtime-certification-v2
- repo_id: thuml/sundial-base-128m
- revision: 3212e42564493f520593e5414af4367fc4b49226
- status: CERTIFIED
- runtime executed: true
- model class: SundialForPrediction
- input series: 7
- context length: 64
- prediction length: 1
- input shape: [7, 64]
- output shape: [7, 1, 1]
- output finite: true
- model device: cuda:0
- input device: cuda:0
- output device: cuda:0
- CPU preprocessing: true
- CPU fallback: false
- PyTorch peak VRAM: 611804160 bytes
- external runtime PID: 83745
- external PID captures: 38
- external GPU memory range: 26-916 MiB
- remote-code review: APPROVED
- license: Apache-2.0 APPROVED
- dedicated test: tests/test_sundial_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/sundial-base/sha256sum.txt OK

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


### toto-open-base

- Branch: feat/toto-open-base-runtime-audit-v1
- Commit: pending
- Push: pending
- repo_id: Datadog/Toto-Open-Base-1.0
- revision: 0411ceb27bdf7fc3e4892e99edc8ad08192dc3c5
- status: BLOCKED
- blocked reason: FIXED_SNAPSHOT_MISSING
- checked snapshot: /mnt/e/env/huggingface/hub/models--Datadog--Toto-Open-Base-1.0/snapshots/0411ceb27bdf7fc3e4892e99edc8ad08192dc3c5
- runtime executed: false
- CPU fallback: false
- license: Apache-2.0 from ledger; pinned local model card/license files are unavailable.
- dedicated test: tests/test_toto_open_base_runtime_audit.py
- hash verification: audit/tsfm-runtime/toto-open-base/sha256sum.txt OK
- resume condition: Install the exact pinned revision into the configured local Hugging Face cache with config.json and model.safetensors present.
