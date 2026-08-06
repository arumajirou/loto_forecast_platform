# Pull Request Plan

## PR-A — contract only

Adds provenance, clean-room license boundary, strict contracts, inactive config,
and focused tests. It must not register or execute the model.

## PR-B — exact kernel and runtime

Adds independently authored context-tree mathematics, online predict-before-update,
state save/reload, manual small-case agreement, and real CPU runtime evidence.

## PR-C — integration

Registers `pp-bayesian-context-tree` in the probabilistic catalog and native
registry, adds explicit builtin dispatch, and integrates CLI/API/TTS only after
PR-B evidence passes.

## PR-D — evaluation

Adds chronological OOF, Holdout, Prospective prediction sealing, required
baselines, multi-seed aggregation, and experiment persistence.

## PR-E — optimization

Adds evidence-gated depth/beta tuning and bounded-lane performance work while
preserving exact-lane parity.

Each phase starts from the latest main after its prerequisite phase is merged.
PR-A makes no claim that later phases exist or will pass.
