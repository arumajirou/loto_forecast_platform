# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P8D_IMPLEMENTED / TARGET_HOST_SEQUENCE_PENDING`.

PR #83 provides P0-P6, PR #86 provides P7, PR #87 provides P8, PR #89 provides P8A, PR #91
provides P8B, and PR #98 provides P8C. P8D adds the target-host control plane that binds these
existing phases into one ordered Run ID without approving dependencies or executing the model.

Preparation creates a control workspace outside the repository. The workspace records the clean
source identity, pinned snapshot path, exact operator commands, current stage, artifact references,
immutable checkpoints, event hash chain, artifact manifest, and SHA-256 sums.

The sequence stops after every external action. A candidate must pass static review before it can be
recorded. An installation must contain an actual human reviewer, timezone-aware review time,
`apply_requested=true`, and matching lock hashes. A campaign is revalidated by P8C before recording.
The final pair report is independently recomputed before P9 can open.

Local pure tests pass. No target-host lock approval, real CPU/CUDA campaign, Uni2TS inference, GPU
evidence, accuracy metric, or successful GitHub Actions step is claimed.
