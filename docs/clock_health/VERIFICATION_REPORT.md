# Verification Report

Status: `PARTIALLY_VERIFIED / FOUNDATION_ONLY`.

## Executed

- focused pytest: 29 passed;
- statement coverage: 85%;
- Python compileall: pass;
- Python AST parse: pass;
- JSON policy parse and strict model load: pass;
- offline CLI healthy fixture: pass;
- evidence manifest and SHA256SUMS verification: pass;
- Python line length at or below 100: pass after final formatting;
- pure evaluator subprocess-import scan: pass;
- fixed argv and `shell=False` scan: pass.

The first focused run detected a stale source-ID `sha256` reference after parser-code hashing was
changed to bind exact source bytes. It was fixed before publication. A second run exposed malformed
tracking being classified as blocked because unknown leap state was converted to `synchronized=false`;
it was corrected to preserve unknown state. The complete focused suite then passed.

## Blocked or not executed

- Ruff: tool unavailable in the isolated environment;
- mypy: tool unavailable in the isolated environment;
- full repository pytest: no complete checkout in this execution environment;
- real chronyc target-host observation: not executed;
- existing Prediction Lock integration: not implemented;
- trusted timestamp, RFC 3161, Sigstore, or public signature: not executed;
- Holdout and Prospective actual access: not executed.

Fixture success validates the project contracts and parser behavior only. It does not certify a real
host clock or establish third-party trust.
