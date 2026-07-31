# Sundial Provider Environment

Dedicated uv project for running the THUML Sundial foundation provider outside
the main application environment.

- Package: `transformers`
- Model repo: `thuml/sundial-base-128m`
- Runtime API: `AutoModelForCausalLM.from_pretrained(..., trust_remote_code=True)`
- Remote code: required; record remote code revision and Python file hashes.
- Runtime status: only report `ZERO_SHOT_PASS` after real local weight loading,
  seven-series prediction, finite shape validation, save/load reference, and
  subprocess reload parity.

Generated artifacts such as Hugging Face cache contents, provider request and
response JSON files, stdout/stderr, GPU evidence, and model manifests are not
source artifacts and should not be committed.
