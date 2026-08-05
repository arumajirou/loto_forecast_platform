# GluonTS P6 nine-model certification matrix

## Scope

P6 generalizes the P5 cross-process Predictor lifecycle from DeepAR to all nine
PyTorch Estimators exported by both GluonTS 0.16.3 and 0.17.0.

The registry is intentionally bounded. It is a runtime certification profile,
not a hyperparameter search space and not an accuracy claim.

## Model matrix

| Model | Module | Trainer | Certified distribution | Context | Minimum target | Bounded profile |
|---|---|---|---|---|---:|---|
| DeepNPTSEstimator | `gluonts.torch.model.deep_npts` | native epochs | intrinsic | explicit, 8 | 32 | hidden `[4]`, 1 epoch, 1 batch/epoch, batch 4 |
| DeepAREstimator | `gluonts.torch.model.deepar` | Lightning | StudentTOutput | explicit, 8 | 32 | 1 layer, hidden 4, 4 samples, 1 epoch |
| TiDEEstimator | `gluonts.torch.model.tide` | Lightning | StudentTOutput | explicit, 8 | 32 | hidden dimensions 4, one encoder/decoder layer |
| SimpleFeedForwardEstimator | `gluonts.torch.model.simple_feedforward` | Lightning | StudentTOutput | explicit, 8 | 24 | hidden `[4]`, 1 epoch, 1 batch/epoch |
| TemporalFusionTransformerEstimator | `gluonts.torch.model.tft` | Lightning | QuantileOutput | explicit, 8 | 32 | quantiles 0.1/0.5/0.9, one head, hidden 4 |
| WaveNetEstimator | `gluonts.torch.model.wavenet` | Lightning | intrinsic | derived by model | 32 | 16 bins, residual/skip 4, depth 1, stack 1 |
| DLinearEstimator | `gluonts.torch.model.d_linear` | Lightning | StudentTOutput | explicit, 8 | 24 | hidden 4, kernel 3, 1 epoch |
| PatchTSTEstimator | `gluonts.torch.model.patch_tst` | Lightning | StudentTOutput | explicit, 8 | 32 | patch 2, stride 1, model 4, one head/layer |
| LagTSTEstimator | `gluonts.torch.model.lag_tst` | Lightning | StudentTOutput | explicit, 8 | 32 | model 4, one head/layer, feedforward 8 |

## Uniform resource limits

Every model is certified under the same outer policy:

```text
outer_workers=8
threads_per_job=1
device=cpu
max_epochs=1
max_batches_per_epoch=1
max_batch_size=4
max_parallel_samples=4
prediction_length=1
seed=1
```

Constructor overrides are fail-closed:

- unknown keys are rejected,
- numeric values may only stay within the bounded profile,
- list shapes cannot change,
- nested trainer keys cannot be added,
- CPU/device fields cannot change,
- runtime constructor signatures are checked before instantiation.

## Cross-process lifecycle

Each model independently executes:

```text
fit process
  registry/version/import/signature/resource checks
  constructor -> dataset -> fit -> predict
  shape -> finite -> observed device
  serialize -> file inventory -> tree SHA-256

new load process
  manifest/tree/dataset/registry/spec/version/PID checks
  deserialize -> predict
  shape -> finite -> observed device -> identity
```

No model inherits another model's successful state. A campaign is `VERIFIED`
only when all nine independent lifecycles are `VERIFIED`.
