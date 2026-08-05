# Model Profiles and Dedicated Harnesses

## Purpose

The profile layer separates model-family-specific behavior from the generic
OpenAI-compatible transport. A profile is applied before the engine call and is
recorded in request metadata and Prometheus metrics.

Pipeline:

```text
ChatRequest
  -> ProfileRegistry.resolve(ModelDescriptor)
  -> ModelProfile.apply(mode, task_type)
  -> engine-specific payload conversion
  -> inference
  -> profile metrics and A/B report
```

## Qwen profile

Profile ID: `qwen3`

Matched by model key or architecture patterns containing `qwen`.

### Qwen3-Coder

Qwen3-Coder instruct models are treated as non-thinking-only. The harness does
not append `/think` or `/no_think` to these models.

Baseline sampling:

- `temperature=0.7`
- `top_p=0.8`
- `top_k=20`
- `repetition_penalty=1.05`

Modes:

- `generic`: no harness tuning; baseline for A/B tests.
- `fast`: non-thinking, bounded output, lower sampling variance.
- `quality`: official Qwen3-Coder sampling baseline.
- `reasoning`: non-thinking sampling plus an explicit arithmetic verification cue.
- `tools`: non-thinking, lower temperature, deterministic tool selection.

### Hybrid-thinking Qwen3 chat models

When the concrete model is not identified as Qwen3-Coder, the profile may use
`/think` and `/no_think` for hybrid-thinking Qwen3 chat models. This is a
model-specific decision rather than a family-wide assumption.

The message contract preserves `reasoning_content` when the provider exposes it,
so multi-step tool histories do not silently discard reasoning state.

The harness does not overwrite the tokenizer-owned Jinja chat template inside
LM Studio. It verifies effective behavior through exact-response, reasoning,
coding, JSON-schema, tool-call, and long-context probes.

## Gemini profile

Profile ID: `gemini-interactions`

The Gemini adapter uses the Gemini Interactions API semantics rather than
pretending Gemini is an OpenAI-compatible server.

Implemented mappings:

- model discovery through the Gemini model listing API;
- `system_instruction` separation;
- user, model, and function-result history steps;
- custom function declarations;
- tool-choice conversion to Gemini `allowed_tools` modes;
- OpenAI-style JSON Schema conversion to Gemini structured output format;
- thought/reasoning step preservation;
- cached-token accounting;
- provider history passthrough for stateless multi-step interactions.

`GEMINI_API_KEY` is read only from the environment. It is never placed in the
configuration or artifact report.

## Acceptance policy

A model profile is not promoted because it exists. It must pass the same task
matrix as the generic baseline and improve the weighted strict achievement rate.

V4.3 reports three separate views:

- `achievement_rate`: strict task success;
- `semantic_achievement_rate`: task capability/correctness;
- `contract_achievement_rate`: output-contract compliance.

Semantic-only improvements cannot trigger promotion. Existing critical-task
floors remain unchanged and automatic promotion remains disabled.

## Upstream references

- Qwen3-Coder-30B-A3B-Instruct model card: https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct
- Qwen concepts and chat/tool templates: https://qwen.readthedocs.io/en/latest/getting_started/concepts.html
- Qwen function calling: https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md
- Gemini Interactions API: https://ai.google.dev/api
- Gemini function calling: https://ai.google.dev/gemini-api/docs/function-calling
- Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output
- Gemini context caching: https://ai.google.dev/gemini-api/docs/caching
