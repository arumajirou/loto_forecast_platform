# Model and engine certification

Inventory is not certification. For each combination of model file SHA, quantization, engine build,
GPU driver, context, KV type, batch, parallel setting, and chat template, record these stages:

```text
DISCOVERED
LOAD_VERIFIED
HEALTH_VERIFIED
INFERENCE_VERIFIED
STRUCTURED_OUTPUT_VERIFIED
TOOL_CALL_VERIFIED
CODE_TASK_VERIFIED
UNLOAD_VERIFIED
VRAM_RELEASE_VERIFIED
CERTIFIED
```

Run the initial suite:

```bash
uv run --extra harness loto-harness certify qwen3-coder-30b-a3b-instruct
```

The suite loads and unloads every tested context independently, then performs a schema-constrained
JSON test and a final unload. Extend it on the real machine with needle retrieval, beginning/middle/
end recall, multi-file coding, tool calls, and repeated cache tests.

A 64K result must record at least:

- final applied context returned by the engine
- model and model-file SHA-256
- engine/runtime version
- prompt template
- GPU/RAM peak
- TTFT and prompt/generation TPS
- JSON schema and tool-call pass rates
- beginning/middle/end retrieval accuracy
- unload and VRAM release
