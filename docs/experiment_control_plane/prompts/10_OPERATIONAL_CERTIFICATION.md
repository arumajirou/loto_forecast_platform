# Stage Prompt: operational-certification

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=operational-certification
```

Additional stage boundary:

Execute an end-to-end synthetic operational certification with failure injection, restart, corruption and rollback; do not open Holdout/Prospective or promote.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
