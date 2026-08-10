# HANDOFF — Windows-only execution

## Repository

```text
repository=arumajirou/loto_forecast_platform
pr=240
branch=feat/timer-base-84m-oof-evaluation-v1
state=open/draft
last_code_bearing_head_before_docs=7795c413d295f445dbdcdf8d85894bf6c81db35a
```

## Completed

- MiniLoto physical/logical identity repair;
- leakage-safe raw baselines;
- immutable prediction sealing;
- Timer Base 84M OOF orchestration foundation;
- focused Windows validation 20/20 PASS;
- Ruff/mypy/py_compile/compileall smoke PASS on code-bearing contents;
- standard Linux CI PASS as historical evidence;
- Windows self-hosted runner restored;
- PowerShell 7.6.4 installed;
- Windows portability run `31353996850`, latest job `93356157095`, 13/13 PASS;
- Windows-only documentation alignment.

## Current operator constraint

```text
native_windows_available=true
linux_available=false
wsl_available=false
```

Do not hand off a Linux-only command as the required next step.

## Current scientific status

```text
scientific_progress=18%
formal_oof=false
timer_inference=false
holdout_opened=false
prospective_opened=false
accuracy_claim=false
champion_claim=false
promotion=false
```

## Next required work

1. Re-fetch the final PR head after documentation commits.
2. Review applicable CI on that final head.
3. Find or transfer the exact frozen development snapshot to Windows.
4. Verify expected snapshot SHA-256 `99c6a9c7fc2c9ce5b5f1b8351841c5ead1aeb48f99e6846c289988af56896053`.
5. Create an isolated clean Windows worktree at the final execution head.
6. Calculate raw-byte `git ls-tree` code hash.
7. Measure Windows CPU/GPU/resource/package identity.
8. Regenerate 10 `EvaluationProtocolV2` artifacts.
9. Verify 10 unique hashes and fix a new `PROTOCOL_SET_SHA256`.
10. Execute baseline OOF.
11. Execute Timer Base 84M OOF.
12. Aggregate all configured seeds and compare against required baselines.

## Do not do

- do not reopen Holdout or Prospective;
- do not reuse stale historical protocol hashes as final hashes;
- do not copy Linux resource identity into Windows protocol evidence;
- do not regenerate a missing frozen snapshot from a database without explicit protocol change;
- do not select only the best seed;
- do not mark the Draft PR ready or merge solely because portability CI passed;
- do not force push or rewrite history.