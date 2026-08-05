# HierarchicalForecast handoff

## Current state

- Pull request: `#48`;
- branch: `agent/hierarchicalforecast-runtime-certification`;
- base: `main`;
- status: `PARTIALLY_VERIFIED / LOCK_CONTRACT_TESTS_PASS / CI_BLOCKED_PRE_RUN`;
- canonical repository CI blocker: `#58`;
- PR-specific dependency tracker: `#61`;
- Draft: retained;
- review-ready authorization: none;
- merge authorization: none.

Resolve the branch head at handoff time:

```bash
git fetch origin agent/hierarchicalforecast-runtime-certification
git rev-parse origin/agent/hierarchicalforecast-runtime-certification
```

The SHA is intentionally not hardcoded because this document is part of the moving branch.

## Implemented scope

- actual upstream `fit_predict()` execution for all ten registered reconcilers;
- grouped-hierarchy compatibility and strict-tree rejection;
- paired in-sample evidence for methods that require it;
- output shape, finite-value, and coherence validation;
- deterministic four-game × ten-method runtime certification;
- exact distribution/module version checks;
- immutable runtime artifacts and portable `SHA256SUMS`;
- deterministic ZIP and SHA-256 sidecar;
- hardlink plus `O_EXCL` no-clobber fallback for `/mnt/e` publication;
- standalone transferred-package verifier;
- target-machine operator with clean Git pre/post evidence;
- locked quality gate with Ruff, mypy, exact focused JUnit, and full pytest;
- promotion gate that verifies all child evidence on one Git commit;
- standard-library dependency-contract validation before provisioning.

## Formal continuation command

```bash
cd /mnt/e/env/ts/loto_forecast_platform-pr48 || exit 1

git fetch origin agent/hierarchicalforecast-runtime-certification
EXPECTED_HEAD="$(git rev-parse origin/agent/hierarchicalforecast-runtime-certification)"

python3 scripts/run_hierarchicalforecast_promotion_gate.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Do not substitute the legacy direct console command for this promotion gate. The complete command
runs dependency validation, locked provisioning, quality checks, runtime certification, package
verification, and Git postflight in the required order.

## Formal acceptance

```text
promotion status                  = LOCAL_GATES_VERIFIED
formal_success                    = true
ready_for_review                  = false
ci_required                       = true
locked version                    = 1.5.1
installed version                 = 1.5.1
focused JUnit                     = 95/0/0
full JUnit failures/errors        = 0/0
runtime expected/executed/passed  = 40/40/40
runtime failed                    = 0
actual execution/rejection rows   = 24/16
standalone package verifier       = VERIFIED
Git pre/post commit               = identical and clean
```

Local acceptance still does not replace GitHub Actions.

## Evidence roots

```text
artifacts/hierarchicalforecast-quality-runs/<quality-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>/
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip.sha256
artifacts/hierarchicalforecast-target-runs/<operator-run-id>/
artifacts/hierarchicalforecast-promotion-runs/<promotion-run-id>/
```

Run IDs are independent. Read the parent reports rather than assuming matching names.

## Current isolated verification

The following is cumulative evidence from separate isolated runs:

| Group | Result |
|---|---:|
| existing reconciliation | 19 passed |
| ten-class matrix | 12 passed |
| runtime certification | 9 passed |
| console entries | 2 passed |
| immutable/portable package | 11 passed |
| standalone package verifier | 7 passed |
| target verification | 9 passed |
| target operator | 6 passed |
| hardened promotion gate | 11 passed |
| quality gate and lock drift | 9 passed |
| **Total** | **95 passed** |

Additional isolated checks:

- compileall: PASS;
- Python lines over 100 characters: 0;
- lock 1.5.1 accepted;
- lock 1.5.0 mutation rejected;
- remote/local blob equality: PASS;
- unresolved inline review threads: 0.

Do not describe these as one exact-head combined run.

## Dependency boundary

`pyproject.toml` declares `hierarchicalforecast>=1.0`; formal exactness comes from the committed
`uv.lock`, which must resolve only 1.5.1, plus the target installed-version probe.

The dependency validator records:

- declared requirement and whether it is exact;
- lock package versions;
- project and lock Python ranges;
- required dev tools;
- `pyproject.toml` SHA-256;
- `uv.lock` SHA-256.

A formal run must stop rather than install an unlocked substitute.

## Remaining blockers

1. Run the complete promotion gate on the exact current branch head.
2. Obtain one combined focused JUnit result of exactly `95/0/0`.
3. Obtain formal Ruff and mypy success.
4. Obtain a repository-wide pytest result with zero failures/errors.
5. Execute real installed HierarchicalForecast 1.5.1 for all 40 cases.
6. Publish and independently verify the real `/mnt/e` ZIP and sidecar.
7. Record all quality/runtime/operator/promotion Run IDs and hashes.
8. Resolve canonical issue #58 with an Actions run containing real successful steps and logs.

Issue #61 records only this PR's dependency on #58. Current Actions failures occur before step
creation, with an empty API step list and no job-log blob. They are not Python test-failure
evidence. Do not repeatedly rerun or append a comment for every unchanged branch head.

## Owner-side CI action

Inspect repository **Settings → Actions → General**, account **Billing & plans → Metered usage /
Budgets and alerts**, repository **Settings → Actions → Runners**, and the failed run page for any
billing, policy, account, or runner banner. If GitHub reports account/repository Actions disabled
and normal settings cannot restore it, contact GitHub Support. Record any materially new finding in
issue #58.

## Evidence to return after execution

Return or record:

- exact Git SHA;
- `git status --short` before and after;
- promotion command exit code;
- promotion Run ID and report path;
- dependency-contract result and both dependency-file SHA-256 values;
- quality Run ID;
- focused and full JUnit totals;
- Ruff, compileall, mypy, and pip-check statuses;
- installed HierarchicalForecast version;
- runtime Run ID;
- 40/40/40/0 summary and 24/16 partition;
- operator Run ID;
- ZIP path, byte size, publication method, and SHA-256;
- sidecar verification result;
- standalone verifier result;
- all evidence-directory `SHA256SUMS` results;
- GitHub Actions run/job IDs with actual step logs.

## Accuracy boundary

No Hit@±1, MAE, MSE, RMSE, position-level Hit@±1, all-position Hit@±1, Holdout, or Prospective
claim is supported by this runtime certification work.

## Prohibited shortcuts

- do not report constructor availability as runtime success;
- do not accept only a successful subset of the 40 cases;
- do not use an unlocked environment;
- do not run formally from a dirty or mismatched commit;
- do not overwrite raw evidence, ZIPs, sidecars, or manifests;
- do not delete incident evidence to obtain a green rerun;
- do not reinterpret strict-tree rejection as actual execution;
- do not claim forecast-accuracy improvement;
- do not force push to reduce the Contents API commit count;
- do not push directly to `main`;
- do not mark ready, merge, or enable auto-merge without explicit approval.

## Recommended next action

First complete the owner-side Actions checks recorded in issue #58. After the external condition is
changed, run the exact formal continuation command above on the target machine. Keep the PR Draft
unless the entire local promotion gate and a real-step GitHub Actions run both pass and the
verification report is updated with every required identifier and hash.
