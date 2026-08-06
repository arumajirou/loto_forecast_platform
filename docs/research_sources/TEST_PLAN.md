# Test Plan

## Focused contract tests

- valid initial registry and exact initial source IDs;
- duplicate source ID and logical model ID rejection;
- malformed, uppercase, shortened, and unpinned formal revision rejection;
- uppercase and malformed SHA-256 rejection;
- duplicate and unsafe artifact path rejection;
- code/weight license separation;
- remote-code policy, safe/unique allowlist, and reviewed-file inventory binding;
- release-state/status consistency, paper identity, and verified-intake completeness;
- concrete HTTPS repository identity and mirror-flag consistency;
- floating package-version rejection;
- nonofficial mirror canonical rejection;
- supersession reference and cycle rejection;
- unknown-field rejection;
- strict bool/int rejection;
- naive datetime rejection;
- duplicate JSON-key rejection;
- deterministic registry hash;
- non-promotional report and record non-claims;
- no active catalog imports;
- CLI report smoke.

## Validation order

1. focused pytest;
2. compileall;
3. AST, JSON, and YAML parsing;
4. Python line-length scan at 100 characters;
5. secret-pattern scan;
6. artifact manifest and SHA256SUMS verification;
7. Ruff;
8. mypy;
9. catalog-isolation regression test;
10. full repository pytest only after a complete repository checkout is available.

Unavailable checks are recorded as `BLOCKED` or `NOT_EXECUTED`, never as `PASS`.
