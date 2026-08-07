# Chronos-2 Handoff

Next operator actions:

1. Generate and review `environments/chronos2-py313/uv.lock` on the target host.
2. Confirm the local Hugging Face snapshot path resolves to revision `29ec3766...`.
3. Run identity, CPU inference, CUDA inference, and reference reload as distinct Run IDs.
4. Save command logs, request/response JSON, Parquet, manifests, `nvidia-smi` samples, and exit codes.
5. Run Ruff, mypy, focused pytest, then the root full test suite.
6. Update runtime certification and verification report with measured evidence.
7. Do not open Holdout or Prospective in this PR.
