# TiRex-2 Contract v2 specification

Input target history is target-major with shape `[target_count, context_length]`. Native model
output is normalized to `[target_count, 9, prediction_length]`. Quantile index 0..8 maps to
q0.1..q0.9 and index 4 is the point forecast.

Successful responses require finite values, monotone quantiles, exact shape, stable series
identity, and no CPU fallback. `samples` is always `null`; no sample-generation capability is
claimed. `pretraining_overlap` remains `UNKNOWN`.
