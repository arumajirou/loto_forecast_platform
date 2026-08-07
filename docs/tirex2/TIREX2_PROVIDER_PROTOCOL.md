# TiRex-2 Provider Protocol

## Request

Schema version 2 rejects unknown fields. It requires the pinned repository and revision,
`local_files_only=true`, GameGeometry, explicit target columns, context-length-consistent target
history, horizon 1/2/5, the exact q0.1-q0.9 inventory, and a prediction issue timestamp.

Future covariates fail closed unless they are known at prediction time, do not depend on future
actuals, and have source timestamps no later than the prediction issue time.

## Response

The response retains:

- all nine quantile matrices with shape `[target_count, prediction_length]`;
- q0.5 as the explicit point forecast;
- model and artifact identity;
- series and horizon identity;
- runtime and GPU evidence;
- `samples=null` and `pretraining_overlap=UNKNOWN`.

A successful CUDA request may not fall back to CPU. A provider reference manifest is not described
as serialized model weights.
