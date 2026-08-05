# TimesFM 2.5 Package / Source Provenance

The stable lane pins `timesfm[torch]==2.0.2`. The source-pinned lane records upstream commit `3dae50b20d7a724981e8ea36cda75578f80dd2dc` separately and is not treated as interchangeable until parity is measured.

| Item | Stable package | Source-pinned lane |
|---|---|---|
| Distribution | PyPI `timesfm==2.0.2` | Git source |
| Source revision | package metadata | `3dae50b20d7a724981e8ea36cda75578f80dd2dc` |
| Runtime status | implemented, not GPU-certified | schema/environment declaration only |
| Numeric parity | not executed | not executed |

The wheel/sdist hashes and checkpoint hashes are recorded as expected provenance values. This PR does not claim that local downloaded bytes were independently re-hashed because package and model downloads were not executed in the connector workspace.
