# MLForecast Runtime Bundle Verification

## Purpose

The runtime certification ZIP is intended to be portable evidence. A recipient must be able to verify it without trusting the machine that created it or extracting untrusted paths first.

The independent verifier checks the ZIP and its sidecar in place:

```bash
uv run --frozen -- \
  python -m loto.mlforecast.bundle \
  --verify-zip artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip \
  --sha256-file artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip.sha256 \
  --report artifacts/mlforecast-runtime-bundles/<RUN_ID>.verification.json
```

Formal success is the JSON status:

```text
BUNDLE_VERIFIED
```

This status verifies transport integrity and the internal artifact contract. It does not turn a source status of `FAILED` into `RUNTIME_CERTIFIED`.

## Verification gates

The verifier rejects:

- ZIP SHA-256 disagreement with the sidecar;
- malformed or multi-line sidecars;
- corrupt ZIP members or CRC failures;
- absolute paths, `..`, non-canonical paths, backslashes, or NUL characters;
- multiple top-level Run IDs;
- invalid Run ID formats;
- duplicate members;
- directory, symlink, device, or encrypted entries;
- excessive entry counts or excessive total uncompressed size;
- missing runtime report, manifest, checksum list, or bundle report;
- disagreement among `RUNTIME_CERTIFICATION.json`, `BUNDLE_VERIFICATION.json`, `ARTIFACT_MANIFEST.json`, and `SHA256SUMS`;
- file sizes or hashes that differ from the manifest;
- unexpected files not represented by the artifact contract;
- certified runs missing the frozen wheel, predictions, trials, or Core/Auto model bundles.

The default limits are 100,000 files and 2 GiB total uncompressed size. They can be lowered with `--max-files` and `--max-uncompressed-bytes`.

## Source-directory hardening

Before creating a ZIP, the bundler now rejects:

- a symlink used as the Run directory;
- any symlink anywhere below the Run directory;
- manifest paths that resolve outside the Run directory;
- an output directory placed inside the source Run directory.

These checks close the gap where resolving a path before testing it could hide a symlink.

## Outputs

A successful one-command certification produces:

```text
artifacts/mlforecast-runtime-certification/<RUN_ID>/**
artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip
artifacts/mlforecast-runtime-bundles/<RUN_ID>.zip.sha256
artifacts/mlforecast-runtime-bundles/<RUN_ID>.verification.json
```

The external verification report records the ZIP SHA-256, source runtime status, member count, total uncompressed bytes, and verification timestamp.

## Boundary

`BUNDLE_VERIFIED` means the portable evidence is internally consistent and has passed the transport and archive safety checks. The runtime itself is formally successful only when the bundled `RUNTIME_CERTIFICATION.json` has status `RUNTIME_CERTIFIED`.
