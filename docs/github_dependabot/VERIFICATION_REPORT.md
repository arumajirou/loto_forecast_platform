# Verification Report — GitHub Dependabot Foundation v1

## Status

`PARTIALLY_VERIFIED / CONFIGURATION_EXECUTED / RUNTIME_ACCEPTANCE_PENDING`

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

## Static review performed

The committed YAML and Python test were manually reviewed for:

- required Dependabot keys and supported ecosystem identifiers;
- bounded schedules and PR limits;
- exact sensitive-dependency exclusion set;
- absence of auto-merge and credential keys;
- Python typing and repository line-length expectations;
- scope isolation from existing CI, dependencies, models and governance state.

This is not a substitute for executing PyYAML, Ruff, compileall or pytest.

## Not executed

- local YAML parse;
- Ruff format and lint;
- compileall;
- focused pytest;
- full pytest and coverage;
- local secret, dependency or large-file scan;
- Dependabot default-branch parse/job;
- generated dependency PR;
- `uv sync --frozen` on a generated PR;
- GitHub Actions success.

The GitHub connector used for this change does not provide a repository checkout or local command
runner. These checks remain `EXECUTION_PENDING`; they are not represented as passed.

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
