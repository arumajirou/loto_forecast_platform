# P8D Test Plan

## State-machine tests

- initial state is closed and points to the supported candidate event;
- all seven events advance in exact order;
- P9 remains closed until the final event;
- skipped, repeated, or reordered events fail;
- modified event payloads or previous-event hashes fail;
- artifact symlinks fail;
- concurrent record lock acquisition fails.

## Candidate and installation tests

- candidate status and static review must both pass;
- candidate violation count must be zero;
- candidate lock SHA-256 is recomputed;
- manifest tampering fails;
- installation must be `INSTALLED` and applied;
- candidate and installed lock SHA-256 values must match;
- reviewer must be non-empty;
- review time must include a timezone.

## Script tests

- generated commands retain the supported-before-CUDA order;
- pair verification precedes final recording;
- approval fields remain placeholders;
- the record CLI never invokes the installer or subprocess execution;
- accepted events create immutable checkpoint files and refresh control manifests.

## Static gates

Run focused pytest, Python compileall, JSON and CSV parsing, line-length inspection, P8D SHA-256
verification, and a simple secret-pattern scan. Real lock resolution, target-host campaigns, Ruff,
mypy, and full repository pytest remain separate gates.
