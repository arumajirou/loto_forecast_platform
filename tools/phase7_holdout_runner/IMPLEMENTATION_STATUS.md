# TAJ-67 implementation status

Status: `EXECUTION_PENDING`

Implemented on branch `agent/phase7-holdout-runner-canonical-v1`:

- exact original runner SHA-256 gate;
- exact canonical serializer Git blob gate;
- immutable-source derivation into a new output directory;
- canonical semantic v1 frozen/replay comparison;
- preservation of legacy semantic SHA fields as audit evidence;
- MLForecast `1.1.0` runtime gate;
- explicit `Differences([1])` legacy state bridge;
- fail-closed source anchor checks;
- derived runner and serializer compile checks;
- manifest recording original and derived identities.

Local isolated focused tests for the derivation utility: `6 passed`.

Not yet executed on the native Windows sealed Phase 7 runner. Holdout and Actual access remain prohibited until exact-runner derivation and development-only replay verification succeed.
