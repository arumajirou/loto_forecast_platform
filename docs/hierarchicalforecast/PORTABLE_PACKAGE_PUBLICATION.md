# Portable immutable package publication

## Status

`IMPLEMENTED / PACKAGE_AND_CONSOLE_TESTS_PASS / REAL_MOUNTED_DRIVE_EXECUTION_PENDING`

This document describes the final publication step for HierarchicalForecast certification ZIPs.
The deterministic ZIP bytes and all evidence verification remain owned by
`package_certification.py`. The formal console command routes final publication through
`portable_package_certification.py`.

## Motivation

The primary target repository is commonly operated from a WSL mounted Windows drive such as:

```text
/mnt/e/env/ts/loto_forecast_platform
```

Hard-link behavior can differ across Linux filesystems and mounted Windows filesystems. A package
must not fail solely because `os.link()` is unavailable, but it must also never replace a
pre-existing evidence ZIP.

## Formal console target

```text
loto-hierarchicalforecast-certify =
  loto.reconciliation.portable_package_certification:main
```

The target-machine operator continues to invoke the same public command:

```bash
uv run --locked loto-hierarchicalforecast-certify
```

## Publication algorithm

1. Verify the runtime directory, checksums, manifest, and certification identity.
2. Build the deterministic ZIP in a temporary file in the destination directory.
3. Verify ZIP members, metadata, archived hashes, and canonical package manifest.
4. Calculate the ZIP SHA-256.
5. Reuse an existing ZIP only when its bytes, structure, and sidecar match exactly.
6. For a new ZIP, attempt no-replace hard-link publication.
7. If hard links are unsupported, create the destination with `O_CREAT | O_EXCL`.
8. Copy bytes, flush, `fsync`, and recompute SHA-256.
9. Publish the sidecar with the same exclusive no-replace policy.
10. Reverify the final ZIP and preserve any conflicting existing path as incident evidence.

## Publication methods

The package result contains:

```text
publication_method = hardlink
publication_method = exclusive_copy
publication_method = reused_existing
```

`exclusive_copy` is not an ordinary overwrite copy. The destination is opened exclusively and the
operation fails if the path already exists.

## Failure behavior

- A pre-existing different ZIP is rejected and not overwritten.
- A pre-existing mismatched sidecar is rejected and not overwritten.
- A concurrently appearing destination is rejected.
- A partial exclusive copy is deleted before returning failure.
- A ZIP that fails post-publication verification is deleted when it was created by the current run.
- A conflicting sidecar is preserved; the current run does not replace it.
- The temporary ZIP is deleted after success or failure.

## Focused evidence

The existing package-test count remains eleven. Tests were strengthened rather than inflated:

- hard-link-unavailable simulation forces the `exclusive_copy` path;
- the final ZIP, sidecar, metadata, manifest, and SHA-256 still verify;
- simulated partial-copy failure leaves no ZIP or sidecar;
- unchanged evidence is reused without overwrite;
- different ZIP and sidecar evidence remains preserved;
- pre-publication verification failure publishes nothing.

Together with the two console-entry tests, the exact published package and console subset produced:

```text
13 passed
compileall PASS
Python lines over 100 characters: 0
remote/local Git blob equality PASS
```

The formal focused-suite contract therefore remains exactly 77 tests.

## Remaining real-machine evidence

The following is still required on the current clean PR head:

```bash
python3 scripts/run_hierarchicalforecast_target_certification.py \
  --expected-git-sha "${EXPECTED_HEAD}"
```

Record the resulting `publication_method`, ZIP SHA-256, sidecar, runtime Run ID, operator Run ID,
and filesystem location. A successful synthetic fallback test does not replace a real mounted-drive
execution.
