# P6 Regression verification

`PARTIALLY_VERIFIED / LOCAL_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- six required regression identities retained;
- negative target and past-covariate lag enforcement;
- future-covariate horizon coverage enforcement;
- likelihood/quantile consistency validation;
- `SKLearnModel` estimator identity and factory requirement;
- position-local and global-sequence execution contracts;
- missing dependency and per-model runtime failure retention;
- unknown argument rejection;
- prediction shape and finite-value validation;
- raw target-frame immutability;
- MLForecast parity SHA-256 stability and tamper sensitivity;
- Python compile, AST parse, YAML parse, and 100-character line checks.

Not executed:

- installation or import of `darts==0.46.1`;
- real sklearn, LightGBM, XGBoost, or CatBoost fitting;
- real static, past, or future covariate behavior;
- real multi-seed OOF or baseline superiority;
- persistence, Torch, CUDA, GPU PID, VRAM, or CPU fallback certification.
