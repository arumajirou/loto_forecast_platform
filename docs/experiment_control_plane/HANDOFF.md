# Handoff

## First implementation

Use `IMPLEMENTATION_PROMPT.md`.

Target:

```text
TARGET_PR=Experiment Plan Contract v1
BRANCH=feat/experiment-plan-contract-v1
PR_MODE=Draft
```

Why first:

- no GitHub settings;
- no Actions dependency;
- no root dependency change;
- no local agent or secret;
- no model/runtime execution;
- establishes the identity used by every later component.

## Required review boundaries

- PR #139 generic GitHub features remain the underlying capability owner.
- PR #137 remains the Promotion authority.
- PR #140 remains the durable lifecycle/outbox design owner.
- PR #141 remains telemetry owner.
- The plan contract uses opaque references until those foundations are merged.

## Not authorized

- merging the documentation PR;
- changing repository settings;
- creating a GitHub App;
- installing a runner;
- executing a paid API call;
- opening Holdout or Prospective Actuals;
- production Registry or deployment mutation.
