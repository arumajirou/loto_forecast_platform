# Probabilistic Execution API, ETA, Parallelism and Japanese TTS

This is a first-class `loto_forecast_platform` capability.  Runtime code lives
under `src/loto/probabilistic`, configuration under `configs/probabilistic`, and
the command surface under `loto3 probabilistic`.

## Security boundary

- The default bind address is `127.0.0.1`.
- Every state-changing endpoint requires a bearer token.
- The API accepts only named profiles and an explicit allow-list of overrides.
- `.env.ppl-api` and `.env.ppl-notify` are local secrets and are ignored by Git.
- Token creation never prints the token to stdout.

## First-class commands

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic api-token-create --root "$PWD"
```

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic api-serve --root "$PWD"
```

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic tts-play \
  --root "$PWD" \
  --text '確率モデルの実行を開始します。' \
  --speaker 3
```

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic run-start \
  --root "$PWD" \
  --profile fast_cpu \
  --no-preflight \
  --outer-workers 8 \
  --max-heavy-cpu-jobs 8 \
  --speech-enabled \
  --no-email-enabled
```

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic run-current --root "$PWD"
```

```bash
cd /path/to/loto_forecast_platform || exit 1
uv run loto3 probabilistic run-stop --root "$PWD"
```

## Parallelism semantics

`outer_workers=8` means at most eight model trials are dispatched concurrently.
It does not mean 100 percent CPU utilisation.  With one numerical thread per
trial on a 32-thread CPU, approximately 25 percent aggregate CPU utilisation is
expected.  The authoritative evidence is `report/parallelism_audit.json`, in
particular `peak_running_total`.

## GPU semantics

The `fast_cpu` profile intentionally sets the GPU execution limit to zero.
Use `fast_gpu` only after the preflight confirms CUDA-enabled PyTorch and JAX.
The scheduler must never silently claim GPU execution after a CPU fallback.

## ETA semantics

ETA is estimated separately for GPU, heavy-CPU and light-CPU resource classes.
Treat `eta_confidence=low` as provisional, especially before any trials in a
resource class have completed.
