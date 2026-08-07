# HierarchicalForecast branch changelog

## Unreleased — PR #48

### Added

- actual upstream HierarchicalForecast `fit_predict()` execution;
- support for all ten registered reconciler class names;
- grouped-hierarchy compatibility checks and explicit strict-tree rejection;
- paired in-sample actual and fitted input support where required;
- output shape, finite-value, and coherence validation;
- deterministic four-game × ten-method runtime certification;
- exact distribution/module version checks;
- atomic runtime evidence, manifests, and portable `SHA256SUMS`;
- deterministic immutable ZIP and SHA-256 sidecar;
- canonical package manifest and ZIP metadata validation;
- portable final publication using hardlink or `O_EXCL` no-clobber copy;
- partial-copy cleanup and immutable existing-package reuse;
- standalone read-only transferred-package verifier;
- target-machine operator with explicit clean Git pre/post evidence;
- sealed local quality gate with locked provisioning, pip check, Ruff, compileall, mypy, exact
  focused JUnit, and repository-wide pytest;
- hardened promotion gate chaining quality, target runtime, and independent package verification;
- standard-library TOML dependency-contract validator;
- dependency-file SHA-256 evidence for `pyproject.toml` and `uv.lock`;
- operational wrappers:
  - `run_hierarchicalforecast_quality_gate.py`;
  - `run_hierarchicalforecast_target_certification.py`;
  - `run_hierarchicalforecast_promotion_gate.py`;
- complete requirements, specification, architecture, data contract, test plan, runbook,
  verification, handoff, package, promotion, quality, CI-blocker, and artifact-manifest documents.

### Changed

- constructor-only `AVAILABLE` is no longer accepted as runtime proof;
- runtime success is `VERIFIED` only after actual execution and validation;
- the formal operator path is now the exact-head promotion wrapper rather than a direct runtime-only
  console invocation;
- formal environment creation uses `uv sync --extra dev --extra full --locked`;
- the heavy repository pytest suite runs only after dependency, static, and focused checks pass;
- focused acceptance is an exact JUnit contract of `95 tests / 0 failures / 0 errors`;
- promotion success remains bounded as `ready_for_review=false` and `ci_required=true`;
- the target operator records explicit top-level `git_commit` evidence;
- child reports, manifests, Run IDs, Git identities, JUnit totals, runtime partitions, and ZIP
  identities are independently rechecked by the promotion gate;
- README, RUNBOOK, HANDOFF, and related documents now use the same promotion command and current
  95-test inventory;
- existing identical ZIPs are verified and reused rather than overwritten;
- mismatched ZIPs and sidecars are preserved as incident evidence.

### Fixed

- sparse reconciler inputs are converted to CSR before upstream execution;
- constructor and `fit_predict()` arguments are filtered against installed signatures;
- unsupported grouped hierarchies fail before strict-tree construction;
- missing paired in-sample evidence fails before execution;
- non-finite, wrong-shape, or incoherent outputs cannot be promoted;
- one method exception no longer terminates the remaining matrix;
- invalid ZIPs are not published before verification;
- filesystems without hardlink support can publish safely by exclusive copy;
- partial-copy failures do not leave a final ZIP;
- existing package and sidecar evidence is not silently replaced;
- path traversal, duplicate members, unsafe checksum paths, symlink components, unexpected files,
  manifest coverage mismatches, and Run ID mismatches are rejected;
- a changed focused-test count cannot pass merely because pytest returned zero;
- Git changes during quality or promotion execution fail the postflight gate;
- lock drift away from HierarchicalForecast 1.5.1 fails before environment provisioning.

### Locked dependency contract

`pyproject.toml` currently declares:

```text
hierarchicalforecast>=1.0
```

This is recorded transparently and is not presented as an exact declaration. Formal execution
requires the committed `uv.lock` to resolve only:

```text
hierarchicalforecast==1.5.1
```

The validator also requires Python 3.13 coverage, the formal dev-tool set, exactly one full-extra
HierarchicalForecast declaration, and retention of the dependency in the root lock package.
Target certification independently verifies the installed version.

### Verification

Cumulative focused evidence across separate isolated runs:

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
- remote/local Git blob equality: PASS;
- unresolved inline review threads: 0.

These results are cumulative and are not yet one exact-head formal invocation.

### Formal acceptance still pending

- dependency validation on the actual target checkout;
- one combined focused run with exact `95/0/0` JUnit totals;
- formal Ruff and mypy success;
- repository-wide pytest with zero failures and errors;
- real installed `hierarchicalforecast==1.5.1` execution for all 40 cases;
- exact runtime summary `40/40/40/0` and method partition `24/16`;
- real `/mnt/e` ZIP publication and standalone re-verification;
- sealed quality, runtime, operator, and promotion evidence for one exact Git commit;
- GitHub Actions with actual successful steps and logs.

### Known external blocker

Issue #61 tracks GitHub Actions jobs that fail before runner step creation. Current evidence has
`steps=null` and no job logs, so it does not show a Python, Ruff, mypy, pytest, or runtime failure.
Repeated manual reruns are avoided until an external runner, billing, concurrency, or repository
Actions condition changes.

### Accuracy boundary

No forecasting accuracy, Hit@±1, MAE, MSE, RMSE, position-level Hit@±1, all-position Hit@±1,
Holdout, or Prospective claim is made by this runtime certification work.

### Safety

- Draft PR retained;
- raw evidence is written under new Run IDs and is not overwritten;
- mismatched ZIP and sidecar evidence is preserved;
- no direct push to `main`;
- no force push;
- no ready transition;
- no auto-merge;
- no merge.
