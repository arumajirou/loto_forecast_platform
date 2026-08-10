# Security Policy

## Reporting a vulnerability

Please do **not** disclose a suspected vulnerability, secret, credential, private data path, or exploitable runner configuration in a public issue.

Use GitHub's private vulnerability reporting flow from the repository **Security** area when that control is available. If private vulnerability reporting is not exposed in the current repository UI, contact the repository owner through GitHub before sharing sensitive technical details publicly.

A useful private report includes:

- affected commit/ref and path;
- impact and attack preconditions;
- minimal reproduction steps;
- whether credentials, self-hosted runners, artifacts, raw data, Holdout, or Prospective boundaries may be affected;
- suggested mitigation if known.

Do not include real secrets in the report when a redacted reproduction is sufficient.

## Self-hosted Actions runners

The repository uses self-hosted runners. Changes that affect Actions permissions, fork-PR guards, checkout credential persistence, runner labels/identity checks, cache/artifact trust, or executable workflow input should be treated as security-sensitive.

A workflow being present in a pull request does not authorize weakening existing fork guards or enabling persistent write credentials.

## Scientific data boundaries

Holdout and Prospective access controls are part of the scientific integrity boundary. A way to access sealed or future evaluation data outside the authorized path should be reported privately even when it is not a conventional software-security vulnerability.

## Supported version

Security fixes target the current `main` branch unless a maintained release explicitly documents a separate support policy. Historical evidence and immutable artifacts are preserved rather than silently rewritten; remediation should use an additive successor/supersession path where required.
