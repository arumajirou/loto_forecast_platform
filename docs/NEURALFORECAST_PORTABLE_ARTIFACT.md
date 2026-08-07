# NeuralForecast portable artifact export

## Purpose

`LINEAGE.json` intentionally records the absolute paths that were used when a
run was created. Rewriting those files after validation would invalidate the
lineage chain and its verification seal.

The portable exporter therefore does **not** rewrite `LINEAGE.json`, source
manifests, verification reports, seals, or SHA manifests. It copies the complete
transitive evidence tree and creates a separate relocation map:

```text
original absolute path -> ZIP package-relative path
```

The verifier uses that map to locate copied evidence after extraction while
continuing to compare the original hashes.

## Preconditions

The target run and every referenced source, predecessor, and API coverage run
must already have:

- `manifest.json` status `PASS`;
- `VERIFICATION_REPORT.json` status `PASS`;
- a current `VERIFICATION_SEAL.json`;
- a complete valid `SHA256SUMS`;
- no symbolic links.

A GPU runtime campaign is represented by the exact `campaign_report.json` file
recorded in lineage. Its recorded SHA-256 must still match.

The exporter is read-only with respect to all source runs. The ZIP output is
rejected when it is placed inside any copied source directory, because adding
that file would invalidate the source verification seal.

## Export command

```bash
uv run loto-auto-campaign \
  export-portable \
  --run artifacts/prospective/<verified-run> \
  --output exports/prospective-<run>.zip
```

The command does not load a campaign configuration. It operates only on the
already verified artifact tree.

A successful result includes:

```text
status=PASS
schema_version=all-auto-portable-artifact-v1
bundle=<absolute ZIP path>
bundle_sha256=<SHA-256>
entry_count=<deduplicated evidence entries>
source_run=<original target run>
```

The output is written to `<name>.zip.partial` first and moved atomically only
after staging verification passes.

## Verify command

```bash
uv run loto-auto-campaign \
  verify-portable \
  --bundle exports/prospective-<run>.zip
```

An extracted directory may also be supplied:

```bash
uv run loto-auto-campaign \
  verify-portable \
  --bundle /path/to/extracted-bundle
```

Verification is read-only. It does not recreate or replace the original run
tree.

## ZIP layout

```text
PORTABLE_MANIFEST.json
PORTABLE_README.md
PORTABLE_SHA256SUMS
payload/
  target/
  dependencies/
    <original-path-hash>-<run-name>/
  files/
    <original-path-hash>-<filename>
```

`payload/target` is the requested run. Dependencies are deduplicated by their
resolved original path and may carry multiple roles, such as both source and
predecessor.

## `PORTABLE_MANIFEST.json`

The manifest records:

- schema version;
- target's original absolute path;
- target package-relative path;
- target verification-seal SHA-256;
- source seal timestamp;
- each entry's kind, original path, relative path, roles, total size, file
  count, and complete path-and-content fingerprint;
- the explicit relocation map;
- a canonical `manifest_content_sha256` that excludes only its own field.

The original absolute paths are retained because unchanged `LINEAGE.json` files
refer to them. They are used only as relocation keys and are not accessed during
portable verification.

## Verification sequence

The portable verifier checks:

1. ZIP member path safety before extraction;
2. duplicate and case-insensitive-collision detection;
3. symbolic-link rejection;
4. complete `PORTABLE_SHA256SUMS` coverage;
5. portable manifest schema and canonical self-hash;
6. unique original and relative paths;
7. per-entry file count, size, and complete tree fingerprint;
8. target seal identity;
9. each copied run's original `SHA256SUMS` and verification seal;
10. every copied run's `LINEAGE.json` chain;
11. relocated source, predecessor, coverage, configuration, data contract,
    promotion gate, and runtime-report hashes.

Every copied run that contains a lineage file is checked, not only the final
target. This proves that the complete transitive HPO -> validation -> OOF ->
Holdout -> Prospective evidence tree is present.

## Deterministic and large-file behavior

For one unchanged verification seal, repeated exports produce byte-identical
ZIP files.

Determinism is achieved by:

- stable entry ordering;
- fixed ZIP timestamps;
- fixed regular-file mode;
- fixed compression settings;
- stable package-relative names derived from original-path hashes;
- the target seal timestamp instead of a new export timestamp.

Files are streamed in 1 MiB blocks for hashing, copying, ZIP creation, and ZIP
extraction. Model files are not loaded into memory with `read_bytes()`.
Zip64 is enabled for large model artifacts.

## Cross-platform path policy

Archive member names reject:

- absolute paths;
- `.` and `..` components;
- backslashes;
- Windows drive syntax such as `C:`;
- Windows reserved names such as `CON`, `NUL`, `COM1`, and `LPT1`;
- control characters;
- trailing spaces or dots;
- exact duplicate paths;
- paths that differ only by character case.

The same checks are applied during creation and before extraction. ZIP members
are also resolved against the extraction root before any file is written.

## Source immutability

The exporter never:

- edits raw or processed run files;
- rewrites absolute paths inside lineage;
- regenerates source `SHA256SUMS`;
- replaces source verification reports or seals;
- stores the ZIP inside the source evidence tree;
- follows symbolic links.

## Failure behavior

Export validation errors are returned by the CLI as structured `FAIL` output and
exit code 2. Existing output ZIP files are not overwritten. A failed export
removes its `.partial` output.

Portable verification returns `FAIL` for malformed ZIPs, missing evidence,
modified content, unsafe paths, stale seals, unresolved relocation keys, or
lineage/hash mismatches.

## Trust boundaries

This feature provides deterministic local content integrity and relocation
verification. It does not provide:

- digital signatures;
- an external trusted timestamp;
- a transparency log;
- encryption or secret redaction;
- protection against an authorized operator replacing the entire ZIP and all
  separately stored expected hashes;
- unlimited protection from storage exhaustion by an intentionally enormous
  untrusted archive.

For external distribution, publish the returned ZIP SHA-256 through a separate
trusted channel or add a future signed artifact-manifest layer.
