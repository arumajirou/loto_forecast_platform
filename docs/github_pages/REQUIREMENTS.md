# Requirements — GitHub Pages Public-Docs Foundation v1

## Functional requirements

- `PAGE-FR-001`: future publication input is limited to `docs-public/**`.
- `PAGE-FR-002`: every source file is UTF-8 text, regular, allowlisted, and size bounded.
- `PAGE-FR-003`: symbolic links and blocked path components fail closed.
- `PAGE-FR-004`: secrets, credential-bearing URLs, local paths, and private hosts
  fail closed.
- `PAGE-FR-005`: HTML local links and embeds cannot escape the public root and must resolve.
- `PAGE-FR-006`: external links use an explicit host allowlist; external embeds default to none.
- `PAGE-FR-007`: audit evidence records path, size, SHA-256, source commit, and policy result.
- `PAGE-FR-008`: local build is deterministic for the same source, commit, and generated time.
- `PAGE-FR-009`: publication and Pages configuration require separate owner approval.
- `PAGE-FR-010`: rollback cannot delete private repository content or alter production state.

## Non-functional requirements

- no root dependency or lock change;
- no JavaScript or external runtime dependency in the initial public site;
- no automatic deployment;
- no credential, callback URL, protected actual, prediction, or runtime artifact publication;
- all unexecuted plan, visibility, and Actions gates remain explicit.

## Acceptance criteria

Repository-local acceptance requires policy validation, focused tests, compileall, deterministic
build evidence, SHA-256 verification, and an owned-path-only diff. Live acceptance additionally
requires a successful default-branch Pages deployment and public URL content verification.
