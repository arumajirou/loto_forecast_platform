# StatsForecast target-host operator

This stacked operator runs the hardened StatsForecast End-to-End entrypoint and collects one
operator-facing evidence directory. It does not alter model parameters, Git, Holdout data,
Prospective actuals, or prediction results.

## Execution

```bash
export LOTO_NOTIFY_SMTP_HOST="smtp.example.com"
export LOTO_NOTIFY_SMTP_PORT="587"
export LOTO_NOTIFY_SMTP_STARTTLS="true"
export LOTO_NOTIFY_SMTP_USER="operator@example.com"
export LOTO_NOTIFY_SMTP_PASSWORD="set-in-the-shell-only"
export LOTO_NOTIFY_EMAIL_FROM="operator@example.com"
export LOTO_NOTIFY_EMAIL_TO="destination@example.com"

PYTHONPATH=src uv run python scripts/run_statsforecast_runtime_operator.py \
  --output-root artifacts/statsforecast-operator \
  --wheelhouse artifacts/statsforecast-offline-bundle \
  --prepare-offline \
  --expected-commit "$(git rev-parse HEAD)" \
  --seed 1 \
  --horizon 1 \
  --tts \
  --email \
  --hold-open
```

For a verified existing wheelhouse, replace `--prepare-offline` with `--offline`.

## Workflow

1. Require an exact clean Git commit.
2. Run the hardened End-to-End API from PR #70.
3. Run Failure Triage automatically when End-to-End is blocked.
4. Never run Bounded Remediation automatically.
5. Write operator, notification, exception, nested End-to-End, Triage, and SHA-256 evidence.
6. Notify by TTS and email only when explicitly enabled.
7. Keep notification failures separate from the runtime decision.

TTS uses the first available executable from `spd-say`, `espeak-ng`, and `espeak`. It passes
the message as one argument and never invokes a shell.

SMTP secrets are read from environment variables only. They are not written to operator
evidence. The report records only whether credentials were present.

`--hold-open` waits for Enter only when standard input is an interactive terminal.

Exit code 0 is reserved for `RUNTIME_CERTIFIED`. Every blocked or failed state exits 2.
This operator certifies runtime integrity only and makes no predictive-accuracy claim.
