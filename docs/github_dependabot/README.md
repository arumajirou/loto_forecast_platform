# GitHub Dependabot Foundation v1

## Status

`EXECUTED_CONFIGURATION / STATIC_REVIEWED / GITHUB_ACCEPTANCE_PENDING`

This package adds bounded Dependabot version updates for the repository's `uv` dependency graph
and GitHub Actions references. It does not upgrade any dependency, modify `uv.lock`, enable
auto-merge, or change the existing CI workflow.

## Provenance

- Repository: `arumajirou/loto_forecast_platform`
- Base branch: `main`
- Base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Implementation branch: `agent/github-dependabot-foundation-v1`
- Design source: Draft PR #139 at
  `814b59d49944b234dafc9deba1cb07b230c9a348`, used read-only with owner authorization
- Actions state at implementation: `ACTIONS_BLOCKED_PRE_RUN` under Issue #58

## Configuration policy

| Ecosystem | Directory | Schedule | Open version-update PR limit |
|---|---|---|---:|
| `uv` | `/` | Monday 09:00 Asia/Tokyo | 3 |
| `github-actions` | `/` | Monday 09:30 Asia/Tokyo | 2 |

Dependabot's default `dependencies` and ecosystem labels are retained. No custom label list is
specified because unknown custom labels are ignored by GitHub. A repository owner may create a
`compatibility-review` label later and add it through a separately reviewed configuration change.

## Grouping policy

Routine minor and patch updates may be grouped to reduce review volume. Major updates remain
individual. The following compatibility-sensitive Python dependencies are excluded from routine
grouping and therefore remain individually reviewable:

- scientific core: NumPy, pandas, Pydantic, scikit-learn, SciPy;
- forecasting/runtime: NeuralForecast, PyTorch, Triton, Transformers, Hugging Face Hub;
- data/API boundaries: PyArrow, FastAPI, Starlette, HTTPX, Optuna Dashboard.

Exclusion from grouping is not an update block. It prevents unrelated sensitive upgrades from
being combined into one routine pull request.

## Required review for generated dependency PRs

A generated PR is not approved merely because Dependabot created it. Reviewers must verify:

1. manifest and `uv.lock` changes are limited to the stated dependency update;
2. Python, Torch, Triton, Transformers, NeuralForecast and CPU/GPU compatibility remain valid;
3. `uv sync --frozen` succeeds on the exact PR head;
4. focused tests and the relevant runtime smoke test pass;
5. no Train/Validation/Holdout/Prospective, evaluation, prediction-lock, registry, promotion,
   approval, canary, or production binding changed;
6. CI status is classified accurately, including Issue #58 pre-run failures;
7. auto-merge remains disabled.

## Authority boundary

Dependabot may propose manifest and lock updates through pull requests. It has no authority to:

- merge or auto-merge a pull request;
- mutate model registry, promotion, approval, canary, or production state;
- alter evaluation evidence or prediction locks;
- publish Holdout or Prospective data;
- add private registry credentials.

## Acceptance boundary

The configuration can be statically reviewed on this branch. GitHub acceptance, Dependabot job
logs, and the first generated update PR can only be verified after the configuration reaches the
default branch. Downstream CI remains blocked while Issue #58 continues to produce jobs without
steps or accessible logs.
