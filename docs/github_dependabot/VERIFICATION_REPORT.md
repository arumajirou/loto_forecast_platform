# Verification Report — GitHub Dependabot Foundation v1

## Status

`PARTIALLY_VERIFIED / CONFIGURATION_EXECUTED / FOCUSED_TESTS_PASSED /
GITHUB_ACCEPTANCE_PENDING`

## Verified repository facts

- Repository: `arumajirou/loto_forecast_platform`
- Visibility and owner: private repository owned by personal account `arumajirou`
- Authenticated repository permission: admin
- Default branch: `main`
- Base SHA at branch creation: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Design PR #139: Open, Draft, unmerged; read-only use explicitly authorized
- Exact implementation branch did not exist before creation
- No `.github/dependabot.yml` or `.github/dependabot.yaml` existed on the verified base
- No same-purpose open or closed Issue was found
- No same-purpose implementation PR was found; PR #139 is design-only

## Official capability facts applied

- Dependabot configuration uses syntax version `2`.
- The configuration belongs at `.github/dependabot.yml` on the default branch.
- `uv` is a supported package ecosystem using the YAML value `uv`.
- GitHub Actions uses the ecosystem value `github-actions` and `directory: "/"`.
- Weekly schedules may define day, time and IANA timezone.
- `groups`, `patterns`, `exclude-patterns`, `update-types`, and
  `open-pull-requests-limit` are supported options.
- Default Dependabot labels are retained because no custom `labels` option is configured.

## Implemented controls

- exactly two ecosystems: `uv` and `github-actions`;
- weekly Monday schedules in `Asia/Tokyo`;
- version-update PR limits of three and two;
- routine minor/patch grouping only;
- compatibility-sensitive Python dependencies excluded from routine grouping;
- major updates remain individual;
- no dependency upgrade or lock change;
- no auto-merge;
- no private registry or credential configuration;
- repository-owned policy test and operations documentation.

## Focused verification executed

Run identity: `dependabot-foundation-isolated-20260806T0815Z`

The exact UTF-8 contents were fetched back from the GitHub branch. Each reconstructed file was
verified against its Git blob SHA before execution.

| Check | Result |
|---|---|
| PyYAML parse and policy inspection | PASS; version 2, ecosystems `uv` and `github-actions` |
| Python compileall for owned test path | PASS; exit 0 |
| focused pytest | PASS; 5 passed in 0.08s |
| maximum line length review | PASS; all owned files at or below 100 characters |
| focused secret-pattern scan | PASS; no matched private-key/token patterns |
| large-file review | PASS; no owned file above 1 MB |
| SHA-256 verification | PASS; 10 of 10 recorded artifacts matched |

The Python process emitted an unrelated `artifact_tool` spreadsheet warmup traceback on stderr,
but compileall and pytest both returned exit code 0. It did not originate from repository code or
the Dependabot test.

## Unavailable or not executed

- Ruff format and lint: `UNAVAILABLE`; the isolated interpreter reported `No module named ruff`;
- mypy: not applicable to this configuration-only test surface and not executed;
- full repository pytest and coverage: not executed because no repository checkout was available;
- full dependency, detect-secrets or repository-wide large-file scan: not executed;
- Dependabot default-branch parse/job: not executable before merge to the default branch;
- generated dependency PR: not yet available;
- `uv sync --frozen` on a generated PR: not yet available;
- GitHub Actions success: blocked by Issue #58.

Unavailable and unexecuted checks are not represented as passed.

## Actions classification

Latest inspected PR #139 CI evidence:

- workflow run: `31083595892`;
- job: `92557810756`;
- conclusion: failure;
- steps: none;
- job log: unavailable with `404 BlobNotFound`.

Classification: `ACTIONS_BLOCKED_PRE_RUN` under Issue #58. No rerun was requested because the
administrative condition had not materially changed.

## Authority boundary verification

- model registry changed: NO
- promotion or approval state changed: NO
- canary or production binding changed: NO
- evaluation or prediction-lock evidence changed: NO
- Holdout or Prospective opened or published: NO
- root dependency or `uv.lock` changed: NO
- existing `.github/workflows/ci.yml` changed: NO
- secret, callback URL or private registry credential committed: NO

## Remaining acceptance evidence

After merge to the default branch, retain:

1. successful Dependabot configuration parse/job for both ecosystems;
2. first generated PR for `uv` and `github-actions`;
3. observed labels, grouping and open-PR bounds;
4. frozen-lock and focused compatibility results on exact generated PR heads;
5. actionable GitHub Actions evidence after Issue #58 is resolved.
