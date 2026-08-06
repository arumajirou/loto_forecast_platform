# Target-host harness verification

Status: `PARTIALLY_VERIFIED`.

Dependency-light checks executed before publication:

- formal matrix expansion: 90 unique cases;
- strict matrix dimensions and ordering;
- request metadata drift rejection;
- exact reviewed-lock SHA-256 enforcement;
- artifact tampering detection;
- deterministic ZIP ordering and timestamp normalization;
- focused pytest, compileall, JSON parsing, line length, shell-free source validation, and secret scan.

Not executed in the authoring environment:

- isolated dependency installation;
- review of a generated uv.lock;
- real Toto snapshot load;
- CPU/CUDA model inference;
- external GPU PID/UUID/VRAM capture;
- real 90-case matrix;
- full repository pytest, Ruff, mypy, or actionable GitHub Actions.
