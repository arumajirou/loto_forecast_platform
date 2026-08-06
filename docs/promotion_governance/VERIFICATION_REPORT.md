# Promotion Governance Foundation Verification Report

## Status

`PARTIALLY_VERIFIED / CONTRACT_TESTS_PASS_IN_SEPARATE_LANES / COMBINED_SUITE_PENDING / REAL_LIFECYCLE_NOT_EXECUTED`

## Implemented

- strict provider-neutral PromotionSubject schema;
- immutable canonical subject SHA-256;
- separate runtime, accuracy, registry and deployment axes;
- common PromotionStatus taxonomy;
- pure fail-closed transition validator;
- conservative read-only compatibility mappings;
- subject-hash, illegal-transition and non-mutation tests;
- architecture and compatibility documentation.

## Hardening follow-up

A post-publication self-review identified and corrected three contract-level gaps:

1. nested Pydantic models are canonicalized from Python values, so timezone-equivalent datetimes
   produce the same subject SHA-256;
2. verified Holdout promotion evidence requires multiple seeds;
3. production-eligible license status requires a verified real evidence artifact.

The Prospective timestamp validator also checks `utcoffset()` rather than relying only on a non-null
`tzinfo` object.

## Executed validation

```text
original focused suite on pre-hardening exact blobs=30 passed in 0.07s
new hardening suite on modified exact local files=5 passed in 0.05s
modified source and new tests compileall=PASS
modified source and new tests AST parse=PASS
modified source and new tests lines over 100 characters=0
```

The 30-test original suite and the 5-test hardening suite were executed in separate local lanes. A
single combined 35-test invocation against the final remote head remains pending and is not claimed.
Ruff and mypy were unavailable. Full repository pytest and real provider migration were not executed.

## Prior GitHub Actions observation

The pre-hardening PR-head workflow ended before any observable workflow step was created:

```text
workflow=ci
run_number=2887
run_id=31082672223
job=test
job_id=92554848211
conclusion=failure
steps=null
logs_url=null
classification=CI_BLOCKED_PRE_RUN
```

Checkout, Python setup, dependency installation, Ruff, compileall, mypy and pytest did not start.
The final hardening head must be inspected separately and must not inherit this classification without
checking its own job payload.

## Explicit non-claims

```text
real promotion executed=false
human approval generated=false
registry mutation executed=false
canary activation executed=false
primary binding changed=false
production binding changed=false
provider P6-P12 migrated=false
combined final-head suite passed=false
real evidence parity proven=false
```

Synthetic tests validate contract logic only. They do not authorize or certify any real candidate.
