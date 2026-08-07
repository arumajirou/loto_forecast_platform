# Version Design

## Purpose

The application version has one authoritative literal:

```text
src/loto/version.py
└── __version__
```

Package metadata, FastAPI metadata, dashboard text, console scripts, integrity-release defaults,
and build metadata consume that value. They must not maintain independent current-version strings.

Historical version numbers remain allowed when they are explicitly part of release history,
comparison tables, migrations, or schema identifiers.

## Canonical version flow

```text
loto.version.__version__
├── setuptools dynamic package metadata
├── loto.__version__ compatibility export
├── FastAPI app.version
├── dashboard title and heading
├── console-script --version output
├── integrity release default
└── BUILD_INFO.json package_version
```

`pyproject.toml` declares the project version as dynamic and instructs setuptools to read
`loto.version.__version__`. This adds no runtime dependency and does not require a root dependency
or lockfile change.

## Console scripts

The installed console scripts delegate through `loto.entrypoints`. The delegates handle
`--version` and `-V` before importing the heavier command modules, then forward all other arguments
to the existing command implementations.

This preserves existing commands and API paths while making version output available consistently
for `loto`, `loto3`, `loto-auto-campaign`, `loto-lab`, and `loto-integrity`.

## BUILD_INFO

`loto-build-info` can create an atomic JSON artifact:

```bash
uv run loto-build-info \
  --output BUILD_INFO.json \
  --repo-root . \
  --build-time 2026-08-06T13:30:00+09:00
```

The fields have separate meanings:

| Field | Meaning |
|---|---|
| `schema_version` | Schema of the BUILD_INFO document, not the application version |
| `package_version` | Canonical application/package version |
| `version_source` | Name of the authoritative Python attribute |
| `installed_distribution_version` | Version reported by installed package metadata, when present |
| `installed_distribution_status` | `MATCH`, `MISMATCH`, or `SOURCE_ONLY` |
| `git_commit` | Git commit from a build environment variable or repository probe |
| `git_dirty` | `true`, `false`, or `null` when unavailable |
| `build_time` | Explicit build timestamp; never silently replaced by runtime time |
| `generated_at` | Time at which the BUILD_INFO document was generated |

`LOTO_BUILD_GIT_COMMIT`, `GITHUB_SHA`, `LOTO_BUILD_GIT_DIRTY`, and `LOTO_BUILD_TIME` may supply
build-system evidence. Invalid or unavailable Git evidence is represented honestly instead of being
fabricated.

## Source-only and package-not-installed behavior

A source checkout must remain importable before installation. If
`importlib.metadata.version("loto-forecast-platform")` is unavailable, the application continues to
use the canonical source version and records:

```text
installed_distribution_version=null
installed_distribution_status=SOURCE_ONLY
```

A present but different installed distribution is recorded as `MISMATCH`. The BUILD_INFO command
returns a nonzero status for that state only when `--require-installed-match` is explicitly used.

## README policy

The README title does not contain the current version. It directs readers to the CLI or package
metadata instead. Version numbers in release-history headings and historical comparison tables are
not interpreted as the current package version.

## Release procedure

1. Change only `loto.version.__version__` for the application version.
2. Update release notes and historical changelog entries as documentation.
3. Run the version-consistency tests.
4. Build package metadata and confirm it equals `loto.__version__`.
5. Generate BUILD_INFO with an explicit build time and immutable Git commit.

## Compatibility

- Existing Python import `loto.__version__` remains available.
- Existing command names and command arguments remain available.
- Existing FastAPI paths remain unchanged.
- No root dependency is added or removed.
- `uv.lock` is intentionally unchanged because the resolved dependency graph is unchanged.

## Rollback

Before merge, close the Draft PR and delete its branch if desired. After merge, revert the PR
normally. No data migration or registry migration is required.
