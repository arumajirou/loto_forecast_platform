# P8 Foundation verification

`PARTIALLY_VERIFIED / LOCAL_FOUNDATION_CONTRACT_VERIFIED / REAL_RUNTIME_BLOCKED`

Executed locally:

- four Foundation model identities retained;
- stable capability-matrix SHA-256;
- immutable revision and offline local-artifact requirements;
- variable input chunk validation and model-specific limits;
- TiRex license and partial-fine-tuning restrictions;
- runtime capability drift and unsupported-covariate rejection;
- zero-shot optimizer-step and parameter-change rejection;
- fine-tuning effectiveness evidence;
- package-level dependency failure retention;
- local, multivariate, and global-sequence fake-runtime execution;
- prediction shape, finite-value, device, and raw-frame checks;
- focused pytest: 12 passed;
- compileall and AST parsing: PASS;
- YAML parsing and 100-character line inspection: PASS.

Not executed:

- installation or import of `darts==0.46.1` Foundation dependencies;
- Hugging Face model downloads or local model-manifest generation;
- real revision resolution or model-weight loading;
- real zero-shot or fine-tuning inference;
- real covariate behavior;
- real CUDA, GPU PID, VRAM, or CPU-fallback certification;
- real OOF, Holdout, Prospective, or Hit@±1 improvement.

GitHub Actions run `30986557539` / #1088, job `92242545039`, failed before
step creation with `steps=null` and no job logs. This is classified
`CI_BLOCKED_PRE_RUN`, not a code or test failure.
