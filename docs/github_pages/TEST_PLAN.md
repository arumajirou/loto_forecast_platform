# Test Plan — GitHub Pages Public-Docs Foundation v1

## Focused checks

```bash
python -m compileall -q scripts/github_pages tests/github_platform
pytest -q tests/github_platform/test_github_pages_public_docs.py
```

The tests verify:

1. the committed public source passes the strict policy;
2. unknown policy keys fail closed;
3. secrets, local paths, and private hosts are rejected;
4. traversal, broken links, and external embeds are rejected;
5. builds are deterministic and contain only approved files plus generated evidence.

## Security checks

- symlink and blocked-path rejection;
- UTF-8 and extension allowlists;
- maximum size enforcement;
- secret and credential-bearing URL patterns;
- local Unix, WSL, macOS, and Windows path patterns;
- private-network and localhost patterns;
- external link and embed host allowlists;
- output manifest and SHA-256 verification.

## Live acceptance

After a separate deployment PR and owner approval:

- confirm the Pages source is GitHub Actions;
- confirm only the audited artifact is uploaded;
- confirm deployment permissions are `contents: read`, `pages: write`, and `id-token: write`;
- confirm the `github-pages` environment and default-branch protection;
- verify the published URL and all required pages;
- verify private repository content is not reachable;
- retain run, job, artifact, deployment, URL, and SHA-256 evidence.
