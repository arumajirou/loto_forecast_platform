# TiRex-2 handoff

Implemented: isolated Contract v2, geometry presets, full quantile normalization, provenance
constants and manifests, trusted-snapshot hash gate, future-covariate chronology validation,
legacy compatibility adapter, dedicated runner, two-process reload certifier, and focused tests.

Pending: lockfile generation in the target host, actual `tirex-2==0.1.1` load/inference, real
separate-process prediction reproduction, GPU certification, real covariate mutation campaign,
OOF, calibration, baseline comparison, Holdout, and Prospective prediction fixing.
The next operational action is no longer direct lock creation inside the runtime lane. Generate a
non-destructive candidate, inspect the complete report, dry-run with the exact SHA-256, then apply
with the explicit approval token. Real `uv` resolution and human dependency approval remain
pending on the target host.
