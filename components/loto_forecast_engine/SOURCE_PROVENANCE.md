# Source provenance

## Integrated component

- Component: `components/loto_forecast_engine`
- Integration date: 2026-08-02
- Integration purpose: internal forecast-engine component used by `components/loto_ops`

## Supplied source archive

- Local archive: `/mnt/e/env/ts/zips/loto_forecast_project-main.zip`
- SHA-256: `dbb8fb4644250d9195e30c62613addb698ffed08c7e48e10af6c5457947b645b`
- Archive root: `loto_forecast_project-main`

The archive was supplied locally and did not contain Git metadata that established
an upstream commit or repository revision.

## Verified local delta from the supplied archive

The integrated source was derived from the supplied archive with the following
previously verified local differences:

- Added dependency: `statsmodels>=0.14.0`
- Added import:
  `from sqlalchemy import inspect as sqlalchemy_inspect`
- Added SQL files:
  - `sql/00_create_schema.sql`
  - `sql/01_create_meta_tables.sql`
  - `sql/02_create_catalog_and_grid_tables.sql`
  - `sql/03_create_nf_automodel_tables.sql`
  - `sql/04_create_log_tables.sql`

Generated metadata, virtual environments, runtime data, caches, backup files and
Office lock files were excluded from the integration.

## License status

No standalone `LICENSE` or `COPYING` file was found in the supplied archive
or integrated source tree during the integration audit.

**The license and redistribution rights are not established by this record.**
Do not infer or assign an open-source license. Public redistribution or external
publication should remain blocked until ownership and licensing are confirmed.

## Runtime verification

The following checks were completed before this record was written:

- Integrated file-manifest and SHA-256 verification
- Package import identity verification
- `loto_forecast.cli --help` smoke test
- `loto_ops` path resolution to the in-repository engine
- Isolation from the stale external editable installation
- Targeted `loto_ops` runtime-repair tests: 6 passed
