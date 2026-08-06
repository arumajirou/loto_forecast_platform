# Stage Prompt: execution-lanes

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=execution-lanes
```

Additional stage boundary:

Implement separate local GPU and paid API lanes with strict runtime/cost evidence, secret boundaries and bounded circuit breakers.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
