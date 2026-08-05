# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P8B_IMPLEMENTED / TARGET_HOST_LOCK_AND_RUNTIME_PENDING`.

PR #83 provides P0-P6 Contract v2, PR #86 provides P7 native covariates, PR #87 provides the P8
two-process certifier, and PR #89 provides the P8A six-case target-host campaign. P8B adds the
isolated lock candidate and human-review gate without opening OOF, Holdout, Prospective, shared
workers, shared catalogs, or production promotion.

P8B no longer treats the presence of `uv.lock` as sufficient evidence. A runtime lane must contain
three mutually verified artifacts before the frozen probe or provider process can start:

- `uv.lock`;
- `LOCK_REVIEW_REPORT.json`;
- `LOCK_REVIEW_APPROVAL.json`.

The candidate builder copies only the lane `pyproject.toml` into a new immutable output directory,
runs `uv lock` there, inventories every locked package and dependency edge, rejects non-registry
VCS/path/editable sources, requires registry artifact hashes, and leaves the lane unchanged. Human
approval requires the exact candidate lock SHA-256, reviewer identity, timezone-aware review time,
and an explicit approval token. Installation is atomic and refuses an existing lock unless its
current SHA-256 is supplied as a replacement guard.

Local pure and mocked-boundary tests pass. No real lock resolution, human approval, frozen target-host
probe, Uni2TS inference, CUDA campaign, full repository test, or successful GitHub Actions step is
claimed.
