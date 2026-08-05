# MLForecast runbook

## 1. Update the branch safely

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git fetch origin
git switch feat/mlforecast-core-automl-contract-v1
git pull --ff-only origin feat/mlforecast-core-automl-contract-v1

git status --short
```

Do not use force pull, force push, or direct main changes.

## 2. Fast local gates

```bash
uv run python -m compileall -q src/loto/mlforecast tests/mlforecast
uv run pytest -q tests/mlforecast
uv run ruff format --check src/loto/mlforecast tests/mlforecast
uv run ruff check src/loto/mlforecast tests/mlforecast
bash -n docs/mlforecast/run_runtime_certification.sh
bash -n docs/mlforecast/build_handoff_bundle.sh
```

Run focused tests first. Repository-wide pytest and CI belong at the final integration stage.

## 3. Runtime certification

```bash
set +e
bash docs/mlforecast/run_runtime_certification.sh
status=$?
set -e

printf 'EXIT_STATUS=%s\n' "$status"
```

Exit classes:

| Code | Meaning |
|---:|---|
| 0 | Runtime certified and portable bundle independently verified |
| 1 | Runtime failed, but valid failure evidence was bundled and verified |
| 2 | Missing prerequisite or unavailable wheel |
| 3 | Wheel SHA-256 mismatch |
| 4 | Invalid or ambiguous Run ID |
| 5 | Source-run bundling failure |
| 6 | Independent ZIP verification failure |

Only exit `0` plus `RUNTIME_CERTIFIED` is formal success.

## 4. Inspect runtime evidence

```bash
RUN_ID="$(basename "$(readlink -f artifacts/mlforecast-runtime-certification/LATEST 2>/dev/null || true)")"

find "artifacts/mlforecast-runtime-certification/$RUN_ID" -maxdepth 3 -type f -printf '%P\n' | sort
cat "artifacts/mlforecast-runtime-certification/$RUN_ID/RUNTIME_CERTIFICATION.json"
sha256sum -c "artifacts/mlforecast-runtime-bundles/$RUN_ID.zip.sha256"
cat "artifacts/mlforecast-runtime-bundles/$RUN_ID.verification.json"
```

When no `LATEST` pointer exists, use the `RUN_ID=` printed by the runtime script.

## 5. Verify a received runtime ZIP

```bash
uv run --frozen -- \
  python -m loto.mlforecast.bundle \
  --verify-zip /absolute/path/<RUN_ID>.zip \
  --sha256 /absolute/path/<RUN_ID>.zip.sha256 \
  --verification-report /absolute/path/<RUN_ID>.verification.json
```

Do not extract an unverified ZIP.

## 6. Build the source handoff ZIP

The MLForecast scope and the shared `pyproject.toml` / `uv.lock` snapshots must be committed and clean.

```bash
bash docs/mlforecast/build_handoff_bundle.sh
```

The script routes both construction and verification through `loto.mlforecast.handoff_guard`. It records the repository commit, branch, and commit timestamp before construction, repeats the check after construction, and deletes the newly created ZIP and sidecar if the repository state changed during the build.

The guard rejects:

- dirty MLForecast paths or dirty shared environment snapshots;
- detached HEAD or malformed commit metadata;
- symlinked repository, ZIP, or sidecar inputs;
- unsafe or non-portable archive paths;
- duplicate, encrypted, non-regular, or CRC-invalid ZIP members;
- excessive member counts or total uncompressed size;
- missing required documentation, source, configuration, tests, or environment snapshots;
- extra members not represented by `ARTIFACT_MANIFEST.json`;
- disagreement among manifest, `SHA256SUMS`, `SOURCE_PROVENANCE.json`, `VERSION`, `FROZEN_BASE_SHA`, and `FROZEN_UPSTREAM.json`.

## 7. Verify a received source handoff ZIP

Use the strict guard, not the compatibility verifier in `handoff.py`:

```bash
uv run --frozen -- \
  python -m loto.mlforecast.handoff_guard \
  --verify \
  --zip /absolute/path/mlforecast-handoff-<SHA>.zip \
  --sha256 /absolute/path/mlforecast-handoff-<SHA>.zip.sha256
```

Expected status: `HANDOFF_VERIFIED`.

This is an integrity and completeness check for the source package. It does not authenticate the publisher and does not replace `RUNTIME_CERTIFIED`.

## 8. Operational monitoring

Certification is CPU-based and single-threaded by contract. Monitor from a separate terminal:

```bash
watch -n 2 '
  printf "=== processes ===\n"
  pgrep -af "loto.mlforecast|mlforecast" || true
  printf "\n=== cpu and memory ===\n"
  ps -o pid,ppid,stat,etime,%cpu,%mem,rss,cmd -C python 2>/dev/null || true
'
```

GPU use is not required for Ridge or AutoRidge certification. Record GPU state only as environment evidence; do not claim GPU acceleration.

## 9. Failure handling

- Preserve the generated Run directory and bundle.
- Do not overwrite raw input or existing Run IDs.
- Record the exact exit code and terminal output.
- Verify failure bundles before sharing them.
- Do not reinterpret `BUNDLE_VERIFIED` as runtime success.
- Do not reinterpret `HANDOFF_VERIFIED` as publisher authentication or runtime success.
- Do not continue to formal campaigns after any runtime lifecycle failure.

## 10. Final integration boundary

Before Ready or merge:

1. exact installed-wheel runtime certification passes;
2. Ruff and focused tests pass in the target environment;
3. no shared-scope changes are present without explicit approval;
4. GitHub Actions failure is either resolved or documented as a runner-level zero-step blocker;
5. the PR remains Draft until evidence is reviewed.
