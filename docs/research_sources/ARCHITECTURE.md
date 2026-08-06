# Architecture

```text
configs/research_sources/registry.v1.json
                  |
                  v
      duplicate-key-safe JSON loader
                  |
                  v
     strict Pydantic v2 contracts
                  |
          cross-record validator
                  |
          +-------+--------+
          |                |
          v                v
 canonical registry     validation report
 SHA-256                non-promotional
```

## Modules

- `common.py`: strict configuration, enums, sentinels, and primitive validators.
- `contracts.py`: repository, artifact, package, license, compatibility, remote-code,
  contamination, verification-report, and non-claim contracts.
- `records.py`: source-record fields and fail-closed intake-state validation.
- `registry_model.py`: cross-record identity, supersession-reference, and cycle validation.
- `models.py`: compatibility facade that preserves the original public import surface.
- `registry.py`: duplicate-key-safe loading, canonical serialization, SHA-256, and reports.
- `cli.py`: validation entrypoint and atomic report output.
- `__init__.py`: narrow public API.

## Boundaries

The package imports none of the following:

- `loto.models.catalog`;
- `loto.models.catalog_full`;
- `loto.probabilistic.catalog`;
- provider workers or dispatch;
- runtime certification;
- Registry/Promotion services;
- data loaders or protected evaluation data.

A later model intake PR reads one accepted source record and performs its own package, snapshot,
remote-code, runtime, OOF, Holdout, Prospective, and production gates. This PR does not connect
those stages.
Registry storage uses `registry.v1.json` as a strict index and `records/*.json` as one immutable source record per file. The loader validates containment and composes the records before applying the Registry contract.
