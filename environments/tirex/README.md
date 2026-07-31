# TiRex Provider Environment

Dedicated uv project for running the TiRex foundation provider outside the main
application environment.

- Package: `tirex-2`
- Model repo: `NX-AI/TiRex-2`
- Runtime API: `from tirex2 import TimeseriesType, load_model`;
  `model.forecast([timeseries], prediction_length, output_type="numpy")`
- Boundary: JSON request/response files only. Do not pickle model or GluonTS
  objects across process boundaries.
- Runtime status: only report `ZERO_SHOT_PASS` after real local weight loading,
  seven-series prediction, finite shape validation, save/load reference, and
  subprocess reload parity.

Generated artifacts such as Hugging Face cache contents, provider request and
response JSON files, stdout/stderr, GPU evidence, and model manifests are not
source artifacts and should not be committed.
