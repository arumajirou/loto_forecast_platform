# Runbook

Dependency-light identity:

```bash
python scripts/run_toto2_4m_provider.py \
  --request /absolute/path/identity-request.json \
  --response /absolute/path/identity-response.json
```

Native-output validation:

```bash
python scripts/run_toto2_4m_provider.py \
  --request /absolute/path/predict-request.json \
  --native-output /absolute/path/native-output.npy \
  --runtime-evidence /absolute/path/runtime-evidence.json \
  --artifact-reference /absolute/path/artifact-reference.json \
  --response /absolute/path/response.json
```

A predict request without isolated-runtime evidence exits 2 and reports `BLOCKED`; it is not treated
as inference success.
