# Harness architecture

## Separation of responsibilities

```text
UI clients
  Hermes / OpenHands / Open WebUI / AnythingLLM / Claude Code
        |
        v
Harness Gateway (no repository mutation)
  - model registry and capability routing
  - token/context compiler
  - compatibility proxy
  - metrics and health
        |
        +--> LM Studio native v1 and OpenAI/Anthropic compatibility APIs
        +--> llama.cpp server or router
        +--> other OpenAI-compatible providers

MCP memory process (no shell execution)
  - append-only events and claims
  - task status
  - code symbol search
        |
        +--> PostgreSQL + pgvector in production
        +--> SQLite in development/tests

Bounded engineering executor / Claude Code (dedicated worktree only)
  - observe, diagnose, plan, checkpoint, change, test, measure, review, judge
  - repeated-failure stop
  - acceptance or rollback
```

## Native and virtual context

- `declared_context`: metadata claim from a model or engine.
- `certified_context`: highest context that passed this machine's quality/resource certification.
- `virtual_context`: candidate source size that can be searched and compressed externally.
- `uncertified_native_cap_tokens`: 32,768 by default.

A model with `declared_context=65536` and `certified_context=0` is not exposed as certified native
64K. Candidate evidence may total 64K or more, but the context compiler reduces it to the 32K
uncertified cap while preserving protected items.

## Write authority

The gateway and memory service are deliberately unable to execute arbitrary shell commands. Only a
bounded executor or a coding agent in a dedicated Git worktree can modify files. A vector-search
result can never authorize a write by itself.
