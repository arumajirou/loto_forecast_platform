# Test Plan

Run in this order:

```text
schema and canonical JSON
parser and adapter
policy decisions
negative/tamper cases
artifact round trip
CLI smoke
compileall and AST/JSON parse
line and secret scan
full repository tests when a complete checkout is available
```

Required cases:

- healthy fixture;
- warning threshold to degraded;
- unsynchronized clock;
- excessive offset;
- excessive dispersion;
- stale sample;
- zero online sources;
- malformed tracking output;
- unknown contract field;
- duplicate JSON key;
- wall/monotonic clock step;
- raw observation tamper;
- policy hash change and hash tamper;
- local health to external-trust promotion rejection;
- fixed chronyc argv and command evidence;
- parser source hash;
- duplicate tracking field;
- continuity hash tamper;
- evidence bundle and CLI round trips;
- artifact tamper rejection;
- pure-core subprocess import prohibition.

Real chronyc host execution, RFC 3161, Sigstore, Prediction Lock integration, Holdout, and
Prospective are outside this foundation test run.
