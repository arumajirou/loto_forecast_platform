# Stage Prompt: evidence-index

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=evidence-index
```

Additional stage boundary:

Implement evidence roles/references, URI secret rejection, content hashing and verification receipts. No production credentials or large artifacts in Git.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
