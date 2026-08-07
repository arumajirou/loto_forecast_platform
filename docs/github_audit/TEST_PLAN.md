# GitHub Repository Audit Test Plan

## 1. Scope

This plan verifies the read-only GitHub repository audit exporter, its Linux and
Windows launchers, report generation, redaction, integrity artifacts, and failure
classification. It does not validate GitHub billing, organization policy, or
browser-only settings.

## 2. Required invariants

1. Repository mutations are never issued.
2. REST collection uses `GET`; GraphQL collection uses query operations only.
3. An inaccessible endpoint is not represented as a verified empty result.
4. Secret values, Actions variable values, webhook callback URLs, and deploy-key
   material are absent from persisted evidence.
5. Every completed run writes machine-readable status, endpoint status, a manifest,
   SHA-256 checksums, and a CRC-valid ZIP archive.
6. Linux and Windows launchers invoke the same Python command surface.

## 3. Focused verification

Linux / WSL:

```bash
bash scripts/verify_github_audit.sh
```

Windows PowerShell:

```powershell
.\scripts\verify_github_audit.ps1
```

The focused lane executes, in repository CI order:

1. Ruff format check
2. Ruff lint
3. `compileall`
4. `tests/test_github_audit.py`
5. CLI self-test

## 4. Live smoke

The live smoke requires authenticated GitHub CLI access and intentionally uses
small limits.

Linux / WSL:

```bash
GITHUB_AUDIT_LIVE=1 bash scripts/verify_github_audit.sh
```

Windows PowerShell:

```powershell
.\scripts\verify_github_audit.ps1 -Live
```

Required evidence:

- CLI exit code
- `SUMMARY.json`
- `tables/endpoint_status.csv`
- `ARTIFACT_MANIFEST.json`
- `SHA256SUMS`
- ZIP and sibling `.zip.sha256`

## 5. Negative tests

- invalid `OWNER/REPO` form returns argparse error
- missing `gh` returns execution failure
- unauthenticated `gh` returns execution failure
- HTTP 403 is classified as `BLOCKED`
- HTTP 404 is classified as `NOT_AVAILABLE`
- rate-limit responses are classified as `RATE_LIMITED`
- a core endpoint failure returns exit code `2`
- a non-core endpoint gap returns `VERIFIED_WITH_GAPS` and exit code `0`
- ZIP CRC failure aborts finalization

## 6. Cross-platform acceptance

Linux acceptance:

- Bash 4+
- `uv` available
- focused verification passes
- optional live smoke produces artifacts

Windows acceptance:

- PowerShell 5.1+ or PowerShell 7+
- `uv` available
- focused verification passes
- optional live smoke produces artifacts
- `-NoPause` suppresses the terminal pause

## 7. Repository-wide acceptance

The PR can be considered ready only after one of the following is recorded:

1. GitHub Actions executes repository steps and passes; or
2. the repository owner records equivalent local evidence for Ruff, compileall,
   focused pytest, and live smoke while the known Actions pre-run blocker remains.

A workflow run with zero steps is not treated as implementation test evidence.
