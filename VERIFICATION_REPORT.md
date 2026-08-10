> **Historical evidence notice — preserved point-in-time report.**  
> This root report verifies the version-single-source change at its original SHA/time; it is not the current whole-repository status.  
> Current repository verification: [`docs/CURRENT_VERIFICATION_REPORT.md`](docs/CURRENT_VERIFICATION_REPORT.md).  
> Current audited status: [`docs/STATUS.md`](docs/STATUS.md).  
> The original evidence below is intentionally retained unchanged.

# Version Single-Source Verification Report

## Status

```text
PARTIALLY_VERIFIED
CORE_VERSION_TESTS_PASS
PACKAGE_METADATA_BUILD_PASS
INSTALLED_CONSOLE_SMOKE_PASS
REPOSITORY_WIDE_VALIDATION_PENDING
MERGE_NOT_PERFORMED
```

## Scope

- Repository: `arumajirou/loto_forecast_platform`
- Default branch: `main`
- Base SHA: `d6d0e5eae5d055ff545cae5467a1d6775c6e5bd0`
- Working branch: `fix/version-single-source-20260806-1330`
- Verified code/test tree before this report-only commit: `7c28a501c7b99005cd0722ce7c29a92bd4e93cf0`

No direct write to `main`, force push, Ready transition, merge, or auto-merge was performed.

## Duplicate implementation check

The repository state was re-fetched before implementation. Searches found no existing version
single-source branch, `BUILD_INFO` branch, or matching pull request. Existing code instead contained
conflicting current-version values:

| Location | Previous value |
|---|---|
| `pyproject.toml` | `3.2.0` |
| `src/loto/__init__.py` | `2.1.0` |
| FastAPI metadata | `2.1.0` |
| dashboard | `2.1` |
| README title | `3.0.0` |
| integrity release default | `3.0.0` |

Historical version references and schema versions are not treated as the current package version.

## Implemented contract

- `loto.version.__version__` is the only current application-version literal.
- Setuptools derives distribution metadata from that attribute.
- `loto.__version__` remains as a compatibility export.
- FastAPI metadata and dashboard output consume the canonical value.
- Installed console scripts report the same version through lightweight delegates.
- BUILD_INFO keeps application version, BUILD_INFO schema, Git commit, dirty state, explicit build
  time, and generation time as separate fields.
- A package-not-installed source checkout reports `SOURCE_ONLY` instead of failing.
- README current-version text is resolved through CLI/package metadata rather than a mutable title.
- No root dependency was added or removed, and `uv.lock` was not modified.

## Executed validation

### Python compile

```text
python -m compileall -q <canonical version modules>
PASS
```

Validated exact branch-equivalent contents for:

- `src/loto/version.py`
- `src/loto/entrypoints.py`
- `src/loto/__init__.py`

Repository-wide compile remains pending because a complete checkout was not available in the
execution container.

### Core focused tests

A dependency-minimal mirror of the exact canonical version, entrypoint, and package metadata changes
was executed with pytest:

```text
6 passed in 0.06s
```

Covered:

- dynamic package version configuration;
- package export consistency;
- all installed console-script version paths;
- `loto3 integrity generate` canonical release injection;
- source-only package metadata fallback;
- explicit MATCH/MISMATCH/SOURCE_ONLY states;
- atomic BUILD_INFO generation.

The committed repository test `tests/test_version.py`, including the real FastAPI/dashboard and
integrity modules, remains pending in the complete repository environment.

### Package metadata build

Executed without installing project dependencies:

```text
python -m pip wheel --no-deps --no-build-isolation .
PASS
wheel=loto_forecast_platform-3.2.0-py3-none-any.whl
METADATA Version=3.2.0
```

### Installed console and BUILD_INFO smoke

The generated wheel was installed into a clean virtual environment with `--no-deps`.

```text
loto --version=3.2.0
loto3 --version=3.2.0
loto-auto-campaign --version=3.2.0
loto-lab --version=3.2.0
loto-integrity --version=3.2.0
loto-build-info --version=3.2.0
installed_distribution_status=MATCH
BUILD_INFO schema_version=1.0.0
Git unavailable state represented as UNAVAILABLE/null
PASS
```

### Import and BUILD_INFO smoke

```text
import loto
loto.__version__ == 3.2.0
source-only installed_distribution_status == SOURCE_ONLY
explicit build time normalized to UTC
PASS
```

### Line-length check

```text
canonical version modules: no line over 100 characters
PASS
```

## Pending validation

| Validation | Status | Reason |
|---|---|---|
| Exact `tests/test_version.py` in full repository | PENDING | Complete repository checkout unavailable in execution container |
| Full Python compile | PENDING | Complete repository checkout unavailable |
| Existing API tests | PENDING | Complete repository checkout unavailable |
| Full pytest | PENDING | Complete repository checkout unavailable |
| Ruff | PENDING | `ruff` module not installed |
| mypy | PENDING | `mypy` module not installed |
| `uv lock --check` | PENDING | `uv`/complete checkout unavailable; lockfile itself is unchanged |
| GitHub Actions | PENDING | No workflow rerun was requested or performed |

Unavailable checks must not be represented as PASS.

## Backward compatibility

- Existing console command names and subcommands are preserved.
- Existing FastAPI paths and response contracts are preserved.
- `loto.__version__` remains importable.
- Existing explicit `--release` values still override the canonical integrity default.
- No database or artifact schema migration is introduced.

## Rollback

Before merge, close the Draft PR and delete its branch if desired. After merge, revert the PR
normally. No data rollback, database migration, dependency rollback, or lockfile regeneration is
required.

## Merge state

```text
DRAFT_REQUIRED=true
READY=false
MERGED=false
AUTO_MERGE=false
```
