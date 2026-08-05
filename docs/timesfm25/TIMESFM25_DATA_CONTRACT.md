# TimesFM 2.5 Data Contract

`history` is a mapping from `series_id` to an equal-length list of finite floats. Keys must exactly equal `series_ids`. `series_ids` length must equal `game_geometry.position_count`.

TimesFM native batch inference is classified as:

```text
supports_batched_univariate=true
supports_joint_multivariate=false
supports_cross_series_attention=false
```
