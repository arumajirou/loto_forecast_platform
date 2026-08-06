# GitHub Pages Public-Docs Foundation v1

## Status

`PROCEED_LOCAL_ONLY / PUBLIC_ALLOWLIST_EXECUTED / DEPLOYMENT_BLOCKED`

This package prepares an explicitly public-only documentation source and a fail-closed local audit
and build pipeline. It does not enable GitHub Pages, add a deployment workflow, alter repository
visibility, or publish a website.

## Provenance

- repository: `arumajirou/loto_forecast_platform`
- base: `main@d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- branch: `agent/github-pages-public-docs-v1`
- design source: Draft PR #139 head
  `814b59d49944b234dafc9deba1cb07b230c9a348`
- design approval: `owner-authorized-draft`
- Actions state: `ACTIONS_BLOCKED_PRE_RUN` under Issue #58

## Public source

Only `docs-public/**` is eligible for a future Pages artifact. Other repository paths are not
implicitly public inputs.

The source contains:

- project purpose and publication disclaimer;
- high-level architecture and authority boundaries;
- evaluation methodology without results or protected actuals;
- security and responsible-disclosure guidance;
- local CSS, `robots.txt`, and a static 404 page.

## Local commands

```bash
python scripts/github_pages/public_docs.py \
  --policy configs/github_pages/public_docs_policy_v1.yaml \
  --source docs-public \
  --source-commit "$(git rev-parse HEAD)" \
  --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  audit --output artifacts/github-pages-audit/<RUN_ID>

python scripts/github_pages/public_docs.py \
  --policy configs/github_pages/public_docs_policy_v1.yaml \
  --source docs-public \
  --source-commit "$(git rev-parse HEAD)" \
  --generated-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  build --output artifacts/github-pages-build/<RUN_ID>/site
```

## Activation boundary

Deployment remains blocked until:

1. Issue #58 becomes `ACTIONS_VERIFIED`;
2. the current GitHub plan's private-repository Pages eligibility is proven;
3. the owner explicitly approves public internet visibility;
4. the exact source commit passes the public-doc audit;
5. a separate deployment PR adds least-privilege Pages workflow and environment controls.

A private repository does not imply a private Pages site.
