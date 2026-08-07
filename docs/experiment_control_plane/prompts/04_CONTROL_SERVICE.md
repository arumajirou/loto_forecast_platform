# Stage Prompt: control-service

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=control-service
```

Additional stage boundary:

Implement idempotent validate/authorize/enqueue/cancel/status/export service and CLI, integrating the canonical lifecycle owner without duplicating transitions.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
