# Changelog

All notable platform changes are recorded here. Current package version values are not duplicated in
this file; release headings are historical records.

## Unreleased

### Changed

- Established `loto.version.__version__` as the single application-version source.
- Derived setuptools package metadata from the canonical Python attribute.
- Made FastAPI metadata, dashboard text, console scripts, and integrity-release defaults consume the
  canonical version.
- Removed the mutable current-version string from the README title.

### Added

- Added atomic `BUILD_INFO.json` generation with separate package version, schema version, Git
  commit, Git dirty state, explicit build time, and generation time fields.
- Added fail-safe source-only behavior when installed package metadata is unavailable.
- Added version-consistency, dashboard, CLI, package-metadata, BUILD_INFO, and README tests.
- Added `VERSION_DESIGN.md` and `VERIFICATION_REPORT.md` documentation.
