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
- source identity re-check after derivation;
- manifest recording original and derived identities;
- `--stop-after-replay` mode that exits after the frozen 4-seed/80-trial replay gate and before sequential Holdout;
- replay-only evidence explicitly records Holdout draws=0, Actuals=0, Holdout executed=false.

The initial derivation utility revision passed 6 isolated focused tests before replay-only mode was added. The current PR head has additional replay-only tests and therefore requires a fresh native-Windows focused test run; no PASS is claimed yet for the updated head.

Not yet executed on the native Windows sealed Phase 7 runner. Holdout and Actual access remain prohibited until exact-runner derivation and development-only replay-only verification succeed.
