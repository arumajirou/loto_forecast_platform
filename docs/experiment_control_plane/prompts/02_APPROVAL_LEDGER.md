# Stage Prompt: approval-ledger

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=approval-ledger
```

Additional stage boundary:

Implement exact-subject approval/revocation contracts, policy decisions and append-only repository semantics. No real enqueue until durable storage is proven.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
