# Stage Prompt: github-projections

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=github-projections
```

Additional stage boundary:

Implement GitHub App Check/comment/Project projections from an outbox. The projection layer must not create approvals or canonical lifecycle state.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
