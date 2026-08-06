# Runbook

1. Validate JSON request with the strict contract.
2. Verify the isolated project declaration and reviewed `uv.lock`.
3. Verify the remote-code review revision, allowlist, SHA-256 values, and approval.
4. Keep `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `local_files_only=true` for PR-B.
5. Reject CUDA requests on any CPU fallback.
6. Store immutable request, response, manifest, logs, exit code, and SHA-256 inventory.
7. Freeze prospective predictions before actuals are known; update only after scoring.

In PR-A, steps 2 and 3 intentionally block and steps 4 through 7 are not executed.
