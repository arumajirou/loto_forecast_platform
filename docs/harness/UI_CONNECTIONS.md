# UI connections

Start the gateway at `http://127.0.0.1:17200`.

## Open WebUI

- OpenAI-compatible base URL: `http://host.docker.internal:17200/v1` from Docker
- API key: a non-secret placeholder unless gateway authentication is added
- Models are returned by `/v1/models`
- Streaming Chat Completions and Embeddings are supported

## OpenHands

- Custom model: `openai/qwen3-coder-30b-a3b-instruct`
- Base URL: `http://host.docker.internal:17200/v1`
- API key: `local-harness`
- Mount only the dedicated harness worktree, not the primary checkout

## Hermes

Hermes can connect directly to LM Studio or to this gateway's OpenAI-compatible API. Direct LM
Studio use exposes LM Studio-specific JIT loading. Gateway use adds routing, context compression,
audit, and common monitoring. Start with the gateway for agent work and direct LM Studio only for
engine diagnostics.

## AnythingLLM

Use the OpenAI-compatible provider with the gateway base URL. Treat it primarily as document/RAG UI
until its tool-call loop passes an end-to-end certification against the selected local model.

## Claude Code

Claude Code remains a coding/review agent rather than a chat UI. The included scripts use explicit
allowed/disallowed tools. `.mcp.json.example` connects Claude to the harness memory and code index.
