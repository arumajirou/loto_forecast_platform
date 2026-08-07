# BasicTS isolated runtime

This environment deliberately does not modify the repository root dependency graph.

Frozen upstream contract:

- package: `BasicTS==1.1.0`
- source repository: `GestaltCogTeam/BasicTS`
- source revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- Python lane: `3.10`
- first increment: CPU only

Resolve and execute from the repository root:

```bash
cd /absolute/path/to/loto_forecast_platform
uv sync --project environments/basicts-py310
PYTHONPATH="$PWD/src" \
  uv run --project environments/basicts-py310 \
  python scripts/run_basicts_provider.py \
  --request /absolute/path/request.json \
  --response /absolute/path/response.json
```

A generated `uv.lock` must be reviewed and committed only after dependency resolution succeeds.
Runtime success is not inferred from package installation or model discovery.
