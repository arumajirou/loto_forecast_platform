# Timer Base 84M PR-A

Status: `PARTIALLY_VERIFIED / CONTRACT_IMPLEMENTED / RUNTIME_NOT_CERTIFIED`.

This directory documents the isolated PR-A foundation for `thuml/timer-base-84m`.
It deliberately provides no checkpoint loading, inference, OOF, Holdout, Prospective,
fine-tuning, shared catalog, worker, CLI, or Web UI integration.

The provider is fail closed while the isolated `uv.lock`, exact Torch pin, and byte-exact
remote-code hashes remain unresolved. `trust_remote_code=True` is prohibited until the
review artifact is explicitly approved.
