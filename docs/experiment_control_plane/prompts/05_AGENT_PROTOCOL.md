# Stage Prompt: agent-protocol

Use `../IMPLEMENTATION_PROMPT.md` in full with:

```text
TARGET_STAGE=agent-protocol
```

Additional stage boundary:

Implement outbound polling, leases/fencing, heartbeat, isolated workspaces, restart and cancellation with a local CPU synthetic executor only.

Do not omit the fresh audit, safety, local gate, artifact, push or Draft PR sections from the authoritative prompt.
