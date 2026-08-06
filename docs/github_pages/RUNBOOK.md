# Runbook — GitHub Pages Public-Docs Foundation v1

## Before publication

1. Verify GitHub plan eligibility for Pages from a private repository.
2. Record the site's resulting visibility and obtain explicit owner approval.
3. Resolve Issue #58 and require real workflow steps and accessible logs.
4. Audit the exact `docs-public/**` source commit.
5. Review every audit finding and SHA-256 entry.
6. Build into a new empty output directory.
7. Inspect the complete artifact inventory before any upload.

## Activation

Activation belongs in a separate PR. Use a custom Pages workflow so the upload source is the
audited `docs-public/**` artifact rather than the full private repository.

The future deploy job must use:

```text
contents: read
pages: write
id-token: write
environment: github-pages
```

Do not add deployment while plan, visibility, owner approval, audit, or Actions evidence is missing.

## Incident handling

### Prohibited content detected

Stop deployment, preserve the audit evidence, remove the source content in a reviewed PR, rotate any
exposed credential outside Git, and inspect Git history and prior deployments.

### Pages publishes unexpected files

Unpublish the site immediately, retain deployment evidence, compare the deployed artifact with
`PUBLIC_SITE_MANIFEST.json`, and roll back the workflow before republishing.

### CI fails before steps

Classify as `ACTIONS_BLOCKED_PRE_RUN`, reference Issue #58, and do not change feature code or rerun
until an administrative condition changes.

## Rollback

Before activation, close the Draft PR. After merge but before deployment, revert this add-only
package normally. After deployment, unpublish Pages first, disable the deployment workflow, retain
evidence, and then revert the public-doc package if required.
