# Timer-S1 PR-A runbook

1. Validate `configs/timer_s1_campaign/model_manifest.json`.
2. Run the identity request through `scripts/run_timer_s1_provider.py`.
3. Expect process exit code 2 and `status=EXECUTION_PENDING`.
4. Run focused tests and static checks.
5. Verify the Timer-S1 SHA-256 inventory.

Do not download the checkpoint or set `trust_remote_code=True` in PR-A.
