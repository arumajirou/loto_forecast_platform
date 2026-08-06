# Security Model

## Threats

- malicious or accidental Issue/comment trigger;
- unreviewed branch code on a self-hosted runner;
- token or API-key exfiltration;
- replayed dispatch;
- forged Check Run/status;
- compromised local runner;
- cross-lane secret leakage;
- credential-bearing artifact URI;
- Project field used as false approval;
- mutable tag or release identity;
- excessive API spend;
- upload of sensitive raw data to GitHub.

## Controls

### Trigger control

- labels and comments never execute directly;
- reviewed plan and scoped approval required;
- `workflow_dispatch` inputs are revalidated against Git content;
- repository dispatch payloads are treated as untrusted.

### Authentication

- GitHub App installation tokens;
- minimal repository selection and permissions;
- one-hour expiry;
- no long-lived PAT for the agent.

### Runner

- ephemeral/JIT runner for short GitHub jobs where practical;
- external runner log retention;
- no unknown PR code;
- no privileged Docker socket;
- clean execution workspace;
- no shared secrets between local and paid-API lanes.

### Secrets

- secrets never appear in plan, Issue, PR, Check output, Project field, or evidence index;
- paid API credentials are released only after budget and approval gates;
- redaction and secret-pattern scans are mandatory.

### Authorization limitation

The repository is currently personal-account-owned. Private collaborators receive write access, so
strong multi-role separation cannot be claimed. Formal multi-user operation should move to an
organization with granular roles or add an independent external approval authority.

## Minimal GitHub App permission target

```text
Metadata: read
Contents: read
Issues: write
Pull requests: write
Checks: write
Actions: read
```

Projects permissions are added only if the Project integration is enabled and verified.
