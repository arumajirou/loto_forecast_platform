# RUNBOOK — Windows-only execution

## Purpose

Operate PR #240 and the Timer Base 84M OOF campaign when only native Windows is currently executable.

## 1. Start every session with exact-state audit

```powershell
$Repo = "arumajirou/loto_forecast_platform"
$Pr = 240

gh auth status

gh api "repos/$Repo/pulls/$Pr" --jq '{state,draft,base:.base.sha,head:.head.sha}'
```

Record the returned head before any mutation or formal evidence generation.

## 2. Verify Windows runtime tools

```powershell
$PSVersionTable.PSVersion
uv --version
python --version
nvidia-smi
```

If GitHub Actions is involved, verify `az-loto-windows` is online and its service is Running.

## 3. Locate the frozen development snapshot

Do not start formal OOF until the expected frozen snapshot is found on Windows.

Expected historical snapshot identity:

```text
99c6a9c7fc2c9ce5b5f1b8351841c5ead1aeb48f99e6846c289988af56896053
```

If it is missing, stop and locate/transfer the immutable evidence. Do not rebuild it from a database as a silent replacement.

## 4. Calculate Windows-safe code hash

Use Python subprocess bytes:

```powershell
@'
import hashlib
import subprocess

head = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
payload = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", head])
print("git_commit=" + head)
print("code_hash=" + hashlib.sha256(payload).hexdigest())
'@ | python -
```

## 5. Final protocol fixation

Create a new evidence directory. Generate 10 protocols for 5 games × 2 layouts. Bind:

- exact Git commit;
- exact code hash;
- frozen data snapshot hash;
- split/feature/baseline/metric identities;
- seeds `42,1729,20260730`;
- Windows resource budget;
- Windows package versions.

Then verify 10 unique hashes and calculate a new `PROTOCOL_SET_SHA256`.

## 6. Formal OOF execution

Run baseline OOF first. For every target:

1. read only context before the target draw;
2. generate prediction;
3. write immutable prediction record;
4. seal SHA-256 + timestamp;
5. verify seal;
6. only then read target actual;
7. score required metrics.

After baseline OOF is valid, execute Timer OOF under the same target/protocol inventory.

## 7. Runtime checks for Timer

Do not accept availability text alone. Verify:

```text
load
input
inference
output shape
finite values
device
GPU PID/VRAM
CPU fallback
```

Reject unrecorded or prohibited CPU fallback.

## 8. Aggregation

For every metric, report all seeds and aggregate mean, population variance, standard deviation, min/max, worst value, and worst seed.

Primary report order:

```text
Hit@±1
position Hit@±1
all-position Hit@±1
MAE
MSE
RMSE
```

## 9. Protected partitions

Holdout and Prospective remain closed. Do not open them automatically after OOF success.

## 10. Stop conditions

Stop if PR head moves, worktree becomes dirty, data hash mismatches, protocol count/hash validation fails, actuals are read before prediction seal, runtime shape/finite/device checks fail, or protected partitions are opened unexpectedly.