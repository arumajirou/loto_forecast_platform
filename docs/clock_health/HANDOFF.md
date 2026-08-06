# Handoff

## Implemented

- isolated `loto.clock_health` foundation;
- default hashed policy;
- operator script;
- synthetic/retained chronyc fixture verification;
- machine-readable reports and artifact integrity.

## Pending

- exact focused tests in a complete repository checkout;
- Ruff and mypy where the tools are available;
- full repository pytest;
- real target-host `chronyc` execution;
- stable-window observation on the intended production host;
- separately reviewed Prediction Lock precondition integration;
- any real third-party trusted-time implementation.

## Integration rule

A later Prediction Lock adapter may consume only a verified decision whose status is `HEALTHY`,
whose observation/policy/decision hashes remain intact, and whose evidence bundle passes complete
verification. It must not map that decision to PR #125 external trust statuses.
