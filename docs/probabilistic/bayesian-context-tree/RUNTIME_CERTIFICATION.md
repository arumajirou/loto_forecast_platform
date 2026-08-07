# Runtime Certification Boundary

PR-A does not execute a model. Formal PR-B certification must require all of the
following from real provider execution, not mocks:

- request validation;
- native context input creation;
- predict-before-update evidence;
- finite categorical probabilities and simplex validation;
- output-shape validation;
- state persistence;
- reload in a different process;
- exact re-prediction for the same input;
- CPU device identity and runtime PID;
- `cpu_fallback=false`;
- process completion and artifact SHA-256 verification.

The planned runtime is CPU-only and has no checkpoint. Therefore GPU UUID and GPU
process VRAM are null in the PR-A contract. A future GPU implementation requires a
separate contract and certification lane.

Synthetic data may validate a verifier or a small mathematical case, but does not
certify real model runtime or forecasting performance.
