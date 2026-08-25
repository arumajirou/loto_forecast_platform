# Forecast MCP operator artifact root runbook

## Status

`ROOT_CAUSE=FORECAST_MCP_OPERATOR_ARTIFACT_PATH_DRIFT`

This runbook separates the operator-owned Forecast MCP approval artifacts from
repository runtime examples and from scientific accuracy evidence.

## Canonical operator-owned root

For the TAJ-69/TAJ-77 target installation, the canonical root is:

```text
/home/az/.local/share/loto-forecast-mcp/route
```

The two canonical filenames are derived from that one root:

```text
numbers3-development-request.json
numbers3-development-request.manifest.json
```

New configuration must set only:

```json
{
  "route": {
    "operator_runtime_root": "/home/az/.local/share/loto-forecast-mcp/route"
  }
}
```

Do not configure the request and manifest as independent paths. The source contract
accepts the old two-key form only as a migration input, and only when both files use
the canonical names in the same directory. A split parent directory fails closed.

## Why this exists

PR #390 introduced a repository-side example that placed the pair below:

```text
/mnt/e/env/ts/loto_forecast_platform/.runtime/forecast-mcp
```

The TAJ-69 target-machine installation later treated the pair as operator-owned and
used the user data root instead. TAJ-77 target certification followed the stale
repository example and therefore stopped before GPU/residency execution when the
repo-local request was absent.

The missing repo-local file is not evidence that no approved pair exists. A recovery
search that scans only `/mnt/e/env/ts` or worktrees also does not cover the user-owned
runtime root.

## Immediate read-only recovery procedure

Do not regenerate or copy the request first. Verify the existing TAJ-69 pair in place.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

PYTHONPATH=src \
python scripts/verify_forecast_mcp_operator_artifacts.py \
  --config /home/az/.config/loto/forecast-mcp.json \
  --operator-runtime-root /home/az/.local/share/loto-forecast-mcp/route \
  --output /mnt/e/env/ts/loto_gpu_runs/operator-artifact-verification.json
```

The verifier is read-only. It requires all of the following before reporting PASS:

- both canonical files exist under the same operator root;
- manifest schema is version 1;
- `data_scope=development`;
- `actuals_used=false`;
- `holdout_used=false`;
- `prospective_used=false`;
- manifest `request_sha256` matches the request bytes;
- operation is `predict`;
- exact Numbers3 geometry and positions are used;
- exact Moirai-2 repository/revision is used;
- device is CUDA and `local_files_only=true`;
- the request binds a verifiable local snapshot.

If this passes, update `/home/az/.config/loto/forecast-mcp.json` so the route contains
the single `operator_runtime_root` value above. Do not copy the pair into the repo.

## Target certification rule

TAJ-77 characterization/certification commands must derive the approved request and
manifest from the configured operator root. They must not hard-code
`repo/.runtime/forecast-mcp` and must not perform a filesystem-wide recovery copy.

When a diagnostic search is needed, include at least these deterministic roots:

```text
/home/az/.local/share/loto-forecast-mcp/route
/mnt/e/env/ts/loto_forecast_platform/.runtime/forecast-mcp   # legacy only
```

The user-owned root is authoritative for the current target installation when the
read-only verifier passes. The repo-local root is migration/legacy evidence only.

## systemd boundary

The Forecast MCP service reads the operator pair from the user data root. The example
unit keeps `ProtectHome=read-only`, explicitly exposes the canonical route as
read-only, and does not grant write access to the repository `.runtime` directory.
Forecast outputs remain writable only under the configured run-artifact root and the
shared GPU lock remains under `/tmp`.

## CI coverage

Source CI now covers the path contract itself:

- one root derives both canonical filenames;
- legacy same-directory pairs normalize to one root;
- split request/manifest parents fail closed;
- an explicit root conflicting with legacy pair paths fails closed;
- non-canonical legacy filenames fail closed.

CI still does not prove that a target-machine operator pair exists. That is a local,
read-only installation gate performed by the verifier above.

## Scientific boundary

The TAJ-69 request history used for runtime E2E may be a deterministic fixture. A PASS
from the operator-artifact verifier or from the Forecast MCP E2E certifies runtime
lineage and safety only:

```text
LLM -> MCP -> Moirai -> CUDA -> prediction -> LLM restore/continuity
```

It does not certify lottery forecast quality. Hit@±1, MAE, MSE, RMSE, per-position
Hit@±1, full-position Hit@±1, Holdout, Prospective, and actual-data scoring require a
separate scientific evaluation run with time-ordered real data and prediction locking.

## Acceptance evidence to retain

For each target verification retain:

- exact Git commit SHA;
- config SHA-256 with secrets masked;
- operator root path;
- request SHA-256;
- manifest SHA-256;
- manifest scope flags;
- exact Moirai repo/revision;
- snapshot verification output;
- verifier JSON output;
- subsequent GPU characterization/certification Run IDs;
- final `SHA256SUMS`.
