# Timer-S1 current state

Status: `PARTIALLY_VERIFIED / PR_A_HARDENED / REAL_RUNTIME_PENDING / CI_BLOCKED_RUNNER_START`.

The canonical repository is `bytedance-research/Timer-S1`. The observed Hub head is
`8911430cc7f32add5c8913afe12e3b05742f5bb2`, and the observed code/weight upload commit is
`0d35f1fe891243453ca1bfa903b5271cf9eb85cb`. Formal model and source revisions remain
`UNPINNED` because every required artifact hash and size was not independently obtained.

PR-A implements strict contracts, structural game geometry, chronology checks, a remote-code
review gate, an isolated environment declaration, a provider skeleton, focused tests, and docs.
A post-publication self-review additionally bound request hashes to manifest records, enforced
finite and monotone response matrices against exact game geometry, required consistent CPU/GPU
runtime evidence, required exact snapshot inventory accounting, and sanitized invalid CLI run IDs.

Focused verification completed with 49 tests passing and 85% focused source coverage. Ruff and
mypy remain unavailable. GitHub Actions failed before creating any workflow step across multiple
unrelated PRs, so no actionable CI code-test result exists. No weight load, remote-code import,
inference, or accuracy claim exists.
