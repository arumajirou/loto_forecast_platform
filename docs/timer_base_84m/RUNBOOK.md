# Runbook

1. Validate JSON request with the strict contract.
2. Verify the isolated project declaration and reviewed `uv.lock`.
3. Verify the remote-code review revision, exact ordered allowlist, SHA-256 values, named
   reviewer, and timezone-aware UTC approval time.
4. Keep `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `local_files_only=true` for PR-B.
5. Reject CUDA requests on any CPU fallback.
6. Store immutable request, response, manifest, logs, exit code, and SHA-256 inventory.
7. Freeze prospective predictions before actuals are known; update only after scoring.

The provider CLI uses exit code 0 only for completed PR-A operations, 1 for invalid requests,
and 2 for correctly blocked pending states. The request and response CLI paths must differ.

In PR-A, steps 2 and 3 intentionally block and steps 4 through 7 are not executed.
