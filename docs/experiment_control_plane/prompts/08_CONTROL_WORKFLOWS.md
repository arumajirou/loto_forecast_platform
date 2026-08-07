# Stage Prompt: control-workflows

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=control-workflows
```

Additional stage boundary:

Implement short manual/control workflows that validate, enqueue/cancel/verify and exit. Never host long experiments; account for Issue #58.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
