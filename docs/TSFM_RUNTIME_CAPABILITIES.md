# TSFM runtime capabilities — code/evidence audit

> **Evidence basis:** current repository runtime artifacts, not catalog prose  
> **Audit base:** `main@0f7585bca90fe9c1578909018a2dc24fcfdc12cb`  
> **Primary aggregate:** `audit/tsfm-runtime/runtime-status.json`  
> **Revision manifest:** `configs/tsfm/verified-revisions.json`

## Summary

The broad TSFM inventory contains 21 audit identities. The current aggregate evidence records:

```text
total_models=21
certified_models=19
blocked_models=2
pending_models=0
judged_models=21
judged_progress_percent=100.0
```

This is **runtime evidence**, not OOF accuracy evidence.

## Per-model reality

| audit model ID | pinned revision | runtime evidence | shared `catalog.py` / provider relationship | important limitation |
|---|---|---|---|---|
| `chronos-2` | `29ec3766d36d6f73f0696f85560a422f50e8498c` | **CERTIFIED** | exact shared spec; `ChronosProvider` | runtime certification does not equal OOF superiority |
| `chronos-bolt-tiny` | `a0e552de83495b5c28c14c71c374f3e33280b340` | **CERTIFIED** | exact shared spec; `ChronosProvider` | requires exact local pinned snapshot in shared path |
| `chronos-t5-base` | `ad294eaacead15db499b740ea4122266dd2a81a2` | **CERTIFIED** | runtime audit/provider runner exists; no exact `chronos-t5-base` shared `ModelSpec` in audited `catalog.py` | runtime-certified identity is not automatically selectable by shared model ID |
| `chronos-t5-small` | `a971ba21945c4f1796b17a91fe69214b5f4ad472` | **CERTIFIED** | exact shared spec; `ChronosProvider` | exact local snapshot required |
| `granite-flowstate-r1` | `05effc6cb39ee16dce9dd0064ed1a76e4b8ff464` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | certification scope must be read from per-model evidence |
| `granite-patchtsmixer` | `90dc5a88d45f032b7dceefb5d814ca2af54f2ff9` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | not automatically shared-routable |
| `granite-patchtst` | `7fe295d8bc8fbac8041b60ab351882634165517f` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | not automatically shared-routable |
| `granite-ttm-r2` | `d6a79570cac0f33d526601cd3a0fc7c80a8f9a2f` | **CERTIFIED** | related shared `granite-ttm` spec + `GraniteTTMProvider`; audit ID differs | do not assume ID/revision equivalence without binding the exact audit identity |
| `kronos-base` | `2b554741eca47781b64468546e77fef3e85130e6` | **CERTIFIED** | dedicated `scripts/run_kronos_base_provider.py`; not a shared `PositionSeriesWorker` spec | native financial OHLCV/K-line contract; `lottery_domain_compatibility_certified=false` |
| `lag-llama` | `72dcfc29da106acfe38250a60f4ae29d1e56a3d9` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | shared research routing must be added/verified separately |
| `moirai-1.0-base` | `4fa939a8800d9da346c0280f3d9aeba0d2d35877` | **BLOCKED** | no exact shared spec | pinned snapshot lacks required config/model weights; CC-BY-NC personal/non-commercial scope |
| `moirai-2.0-small` | `30f43ff08c8494f4943ae1521e9d4e94a0fbb389` | **CERTIFIED** | related shared `moirai` spec + `MoiraiProvider` | audit says `lottery_domain_compatibility_certified=false`; personal/non-commercial license scope |
| `moment-1-large` | `ca58581bc7bea2ebed4e80dc0a3e4b8b609c6ecc` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | evidence can be execution-only; pretrained forecasting head may require fine-tuning |
| `moment-1-small` | `411e288267f82cce86296dbe4d6c8bc533cc162f` | **CERTIFIED** | runtime audit exists; no exact shared `ModelSpec` | inspect per-model forecast-head scope before use |
| `sundial-base` | `3212e42564493f520593e5414af4367fc4b49226` | **CERTIFIED** | related shared `sundial` spec + `SundialProvider` | shared ID differs from audit ID; bind exact revision/artifacts |
| `t0-alpha` | `f8727c2357e0d81f1d9f56fe3aaac43068b5fc72` | **BLOCKED** | no shared runnable spec | gated access required; commercial deployment not certified |
| `tabpfn-ts` | `4972a65a1b30806315c6f92499959ffbfc69a673` | **CERTIFIED** | exact shared model ID; `TabPFNTSProvider` | candidate/tabular foundation path, not ordinary position TSFM |
| `timesfm-2.5-transformers` | `5a9806b9b291fad9233b5249d88263f1846304d3` | **CERTIFIED** | related shared `timesfm-2.5` + `TimesFMProvider`; shared catalog identity/package differs | verify exact implementation identity before treating the two IDs as equivalent |
| `tirex-2` | `05e5b26db52bfb256f1ae1bdf785589850482de3` | **CERTIFIED** | related shared `tirex` spec uses `NX-AI/TiRex-2`; `TiRexProvider` | shared logical ID differs from audit ID |
| `toto-2.0-4m` | `8306a9801cf98c0f5ffe4b2dcc8f496e616d84d9` | **CERTIFIED** | dedicated runtime evidence/provider work; no exact shared registry entry | not automatically routed by `PositionSeriesWorker` foundation registry |
| `toto-open-base` | `0411ceb27bdf7fc3e4892e99edc8ad08192dc3c5` | **CERTIFIED** | dedicated runtime evidence/provider work; no exact shared registry entry | not automatically routed by shared foundation registry |

## Runtime evidence examples

### Chronos 2

The aggregate current artifact records, among other fields:

```text
runtime_status=CERTIFIED
runtime_device=cuda:0
runtime_gpu_used=true
runtime_cpu_fallback=false
runtime_peak_vram_bytes=497113088
runtime_prediction_shape=[7]
runtime_context_length=512
runtime_prediction_length=1
runtime_cross_learning=false
```

It also records exact weight/config SHA-256 and runtime quantile/mean shapes.

### Kronos Base

The actual provider script fixes:

```text
MODEL_REPO_ID=NeoQuasar/Kronos-base
MODEL_REVISION=2b554741eca47781b64468546e77fef3e85130e6
TOKENIZER_REPO_ID=NeoQuasar/Kronos-Tokenizer-base
TOKENIZER_REVISION=0e0117387f39004a9016484a186a908917e22426
PREDICTION_LENGTH=4
EXPECTED_COLUMNS=open,high,low,close,volume,amount
```

It requires CUDA, local pinned snapshots, validates files/hashes, runs the tokenizer/model, verifies `[4,6]` output, finite values, model/tokenizer CUDA placement and positive VRAM. The returned evidence explicitly sets:

```text
native_domain=financial_ohlcv_kline
lottery_domain_compatibility_certified=false
forecast_accuracy_certified=false
```

Thus Kronos is a concrete example of why runtime certification must not be presented as lottery-model readiness.

### Moirai 1.0 Base

Current aggregate evidence records:

```text
runtime_status=BLOCKED
runtime_blocked_reason=MODEL_WEIGHTS_MISSING
runtime_missing_files=config.json, model weight file
runtime_license_scope=PERSONAL_NONCOMMERCIAL_ONLY
```

### T0 Alpha

Per-model certification artifact records:

```text
runtime_status=BLOCKED
blocked_reason=GATED_ACCESS_REQUIRED
commercial_deployment_certified=false
```

## Shared provider registry versus audit inventory

The shared provider registry is narrower than the 21-model audit inventory. It currently has concrete provider classes for:

```text
Chronos family
Sundial
TimesFM
Granite TTM
TiRex
Moirai
TabPFN-TS
```

`get_foundation_provider()` falls back to `ProviderNotImplemented` when neither the model ID nor library has a registered provider. Therefore a model can have historical/isolated runtime certification evidence and still not be selectable through the normal shared `PositionSeriesWorker` path.

## Revision pinning

`configs/tsfm/verified-revisions.json` contains a verified immutable revision for each of the 21 audit identities. This is separate from the broad catalog's base `revision_status`.

Interpretation:

```text
verified revision manifest
  proves: audited repo/revision identity was fixed
  does not prove: runtime inference passed

runtime certification artifact
  proves: the recorded runtime contract passed for that exact identity/scope
  does not prove: lottery-domain compatibility or forecast quality

OOF evidence
  required for: Hit@±1 / MAE / MSE / RMSE scientific comparison
```

## Aggregate rate inconsistency

The current aggregate artifact simultaneously contains:

```text
certified_models=19
total_models=21
formal_certification_rate_percent=42.9
```

The arithmetic rate for 19/21 is approximately 90.5%. The stored 42.9 field therefore reflects a stale/older definition or stale aggregation and must not be quoted as the arithmetic current certification rate without qualification.

The historical artifact is not rewritten by this documentation audit. A future generator/evidence repair should produce a new evidence identity rather than silently modifying prior evidence.

## Scientific gate

None of the 19 runtime-certified TSFM identities should be promoted merely from this table. Formal scientific use requires the exact lottery data contract, chronological OOF, required baselines, all configured seeds, Hit@±1-first reporting, prediction-before-actual sealing, runtime/license eligibility and later Holdout/Prospective gates.