# Handoff — GitHub Pages Public-Docs Foundation v1

## Current state

The public source, audit policy, build CLI, tests, and operating documents are committed on
`agent/github-pages-public-docs-v1`. Deployment is intentionally absent.

## Reviewer focus

- approve the exact `docs-public/**` content;
- review the blocked patterns, path rules, host allowlists, and file-size limit;
- inspect deterministic manifest and build behavior;
- confirm no private repository path is implicitly included;
- verify the plan and public-visibility gate remains mandatory;
- keep deployment separate from this PR while Issue #58 is unresolved.

## Next safe work

1. run repository-native Ruff, focused tests, and one final full pytest;
2. verify GitHub plan and Pages visibility in Settings;
3. explicitly approve or reject public publication;
4. resolve Issue #58;
5. create a separate deployment PR from current `main`;
6. verify the exact deployed artifact and public URL before marking the feature verified.
