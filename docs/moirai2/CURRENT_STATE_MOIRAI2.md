# Current State: Moirai 2.0

Status: `PARTIALLY_VERIFIED / P0_P8C_IMPLEMENTED / REAL_RUNTIME_EVIDENCE_PAIR_PENDING`.

PR #83 provides P0-P6 Contract v2, PR #86 provides P7 native covariates, PR #87 provides the P8
two-process certifier, PR #89 provides the P8A six-case campaign, and PR #91 provides the P8B
reviewed-lock workflow. P8C adds an independent evidence gate without opening OOF, Holdout,
Prospective, shared workers, shared catalogs, or production promotion.

Formal campaigns must now be launched through `scripts/run_moirai2_runtime_campaign_p8c.py`. The
wrapper captures a clean Git commit, tree, and principal-source SHA-256 identity before invoking the
existing P8A runner, then seals the campaign output with launch evidence and regenerated manifests.

P8C independently reopens every artifact from one supported CPU campaign and one CUDA13 campaign.
It recalculates all file hashes, validates all six cases per lane, rechecks both provider responses,
all nine quantiles, device and CPU-fallback evidence, reviewed-lock identity, snapshot identity, and
rederives CUDA PID, UUID, VRAM, and post-exit release from GPU monitor samples.

`p9_oof_gate_open=true` is possible only after both complete campaigns pass under the same clean
source commit/tree and the same pinned model config and weight hashes. Local pure tests pass. No real
lock approval, real campaign, Uni2TS inference, GPU evidence, accuracy metric, or successful GitHub
Actions step is claimed.
