# Artifact Manifest — GitHub Pages Public-Docs Foundation v1

## Identity

- feature: `pages`
- branch: `agent/github-pages-public-docs-v1`
- base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- design: PR #139 head `814b59d49944b234dafc9deba1cb07b230c9a348`
- status: `PROCEED_LOCAL_ONLY / DEPLOYMENT_BLOCKED`

## Included groups

- `docs-public/**`: reviewed public-only source;
- `configs/github_pages/**`: strict audit policy;
- `scripts/github_pages/**`: audit and local build implementation;
- `tests/github_platform/test_github_pages_public_docs.py`: focused policy tests;
- `docs/github_pages/**`: requirements, operations, verification, handoff, and integrity evidence.

## Excluded

- `.github/workflows/**`;
- root dependencies and `uv.lock`;
- private documentation outside `docs-public/**`;
- runs, artifacts, logs, databases, models, raw data, Holdout, Prospective, and predictions;
- secrets, callback URLs, private hostnames, and local paths;
- Pages settings, environment, custom domain, or deployment state.

`SHA256SUMS` covers every managed file except itself and must be regenerated after any change.

## Verification states

- exact source audit: PASS
- deterministic local build: PASS
- compileall: PASS
- focused pytest: PASS, 5 tests
- managed-source line length: PASS
- focused secret-pattern and size checks: PASS
- SHA-256: PASS after manifest generation
- Ruff: UNAVAILABLE
- full repository pytest: EXECUTION_PENDING
- GitHub Pages activation: BLOCKED
