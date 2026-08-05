# Runtime preflight verification report

Status:

`LOCAL_PREFLIGHT_CONTRACT_VERIFIED / REAL_ENVIRONMENT_BLOCKED`

Executed locally with injected fake package, import, CUDA, and `nvidia-smi` probes:

- strict profile schema and exact `darts==0.46.1` pin;
- unsafe lockfile-path rejection;
- missing lockfile classification;
- exact package-version drift detection;
- required versus optional import classification;
- required Darts model-export validation;
- CUDA-required but unavailable classification;
- CUDA allocation, synchronization, device, memory, PID, and VRAM evidence;
- malformed `nvidia-smi` output rejection;
- deterministic and tamper-sensitive report SHA-256;
- focused pytest: 12 passed;
- compileall and AST parsing: PASS;
- YAML parsing and 100-character line inspection: PASS.

Not executed:

- real uv resolution;
- real notorch or torch lock generation;
- real Darts 0.46.1 installation;
- real optional package imports;
- real CUDA allocation or `nvidia-smi` process evidence;
- real model construction, fitting, prediction, or accuracy.
