# GluonTS P6B nine-model lifecycle matrix

P6A records constructor compatibility and explicitly tested distribution variants. P6B executes one
bounded lifecycle per estimator: fit, predict, serialize, process restart, deserialize, and
re-predict. P6B does not replace the broader P6A distribution matrix.

| Model | P6B output mode | Context | Bounded profile |
|---|---|---|---|
| DeepNPTSEstimator | default | explicit 8 | 1 epoch, 1 batch/epoch, batch 4 |
| DeepAREstimator | StudentTOutput | explicit 8 | one layer, hidden 4, 4 samples |
| TiDEEstimator | default | default | 1 epoch, 1 batch/epoch, batch 4 |
| SimpleFeedForwardEstimator | default | default | hidden `[4]`, batch 4 |
| TemporalFusionTransformerEstimator | StudentTOutput | default | one head, hidden/variable 4 |
| WaveNetEstimator | default | derived | 4 samples, batch 4 |
| DLinearEstimator | default | default | hidden 4, kernel 3 |
| PatchTSTEstimator | default | default | patch length 16, batch 4 |
| LagTSTEstimator | default | default | 1 epoch, 1 batch/epoch, batch 4 |

These combinations are exercised by upstream `test/torch/model/test_estimators.py`. QuantileOutput
and additional DeepAR output variants remain recorded by P6A and require separate lifecycle runs
before formal promotion.

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

Unknown arguments, larger capacities, distribution substitution, signature changes, artifact drift,
and same-process reload fail closed.
