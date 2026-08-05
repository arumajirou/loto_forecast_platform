# Runtime bootstrap verification

Status: `LOCAL_BOOTSTRAP_CONTRACT_VERIFIED / REAL_LOCK_SYNC_PREFLIGHT_BLOCKED`

Local contract checks:

- unsafe and inconsistent paths rejected;
- missing project manifest and missing `uv` blocked;
- stale approval removed before execution;
- lock command failure stops sync and preflight;
- non-empty lockfile and post-lock SHA-256 required;
- frozen sync required before preflight;
- exact command order and `--frozen` arguments retained;
- malformed, stale, or hash-mismatched preflight reports rejected;
- preflight exit-code and JSON-status parity required;
- approval generated only after a passing preflight;
- approval binds lock, preflight, and bootstrap hashes;
- deterministic report and approval hashes are tamper-sensitive.

Focused pytest: 12 passed. Compileall, AST parse, YAML parse, and 100-character line
inspection passed.

Not executed: real `uv lock`, real package download, real frozen sync, real Darts import,
real CUDA allocation, real `nvidia-smi` process evidence, model fit, prediction, or accuracy.
