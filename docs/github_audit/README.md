# GitHub Repository Audit Documentation

This directory contains the operational and verification documents for the
read-only repository audit exporter.

## Documents

- [`../GITHUB_AUDIT.md`](../GITHUB_AUDIT.md): user guide and command reference
- [`TEST_PLAN.md`](TEST_PLAN.md): invariants, focused tests, live smoke, and acceptance
- [`RUNBOOK.md`](RUNBOOK.md): Linux, WSL, and Windows operations
- [`VERIFICATION_REPORT.md`](VERIFICATION_REPORT.md): current PR evidence and blockers

## Commands

Linux / WSL focused verification:

```bash
bash scripts/verify_github_audit.sh
```

Linux / WSL verification with bounded live GitHub smoke:

```bash
GITHUB_AUDIT_LIVE=1 bash scripts/verify_github_audit.sh
```

Windows focused verification:

```powershell
.\scripts\verify_github_audit.ps1
```

Windows verification with bounded live GitHub smoke:

```powershell
.\scripts\verify_github_audit.ps1 -Live
```

Production-style deep audit:

```bash
bash scripts/run_github_audit.sh
```

```powershell
.\scripts\run_github_audit.ps1 -Deep
```
