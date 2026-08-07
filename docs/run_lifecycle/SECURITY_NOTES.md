# Security Notes

- Strict schemas reject unknown fields and unsafe identifiers.
- Canonical JSON rejects duplicate keys, unsupported types and non-finite numbers.
- No command uses shell interpolation.
- Evidence references contain hashes and identities, not secrets or raw protected data.
- Idempotency excludes volatile request, trace, process and lease identity.
- Fencing prevents an expired worker from mutating state after takeover.
- Local SHA-256 and local UTC are not trusted third-party evidence.
- The in-memory repository must not be exposed as production durability.
- API authentication, authorization and tenant isolation are outside this package.
