# HierarchicalForecast standalone package verifier

## Purpose

Verify an existing HierarchicalForecast runtime ZIP and its SHA-256 sidecar without rerunning the
forecasting library, certification harness, or package publisher.

The verifier is intended for handoff, archival retrieval, offline review, and transfer validation.
It uses only the Python standard library and does not modify the supplied evidence.

## Command

```bash
uv run --locked loto-hierarchicalforecast-verify-package \
  --zip artifacts/hierarchicalforecast-runtime/<runtime-run-id>.zip
```

The default sidecar is:

```text
<runtime-run-id>.zip.sha256
```

A different sidecar path may be supplied explicitly:

```bash
uv run --locked loto-hierarchicalforecast-verify-package \
  --zip /path/to/<runtime-run-id>.zip \
  --sidecar /path/to/<runtime-run-id>.zip.sha256
```

The default expected certification status is `VERIFIED`. To inspect a deliberately retained
non-success package, provide its exact status:

```bash
uv run --locked loto-hierarchicalforecast-verify-package \
  --zip /path/to/<runtime-run-id>.zip \
  --expected-status BLOCKED_DEPENDENCY
```

## Independent checks

The verifier recomputes and validates:

- ZIP SHA-256;
- exact sidecar contents;
- regular-file and non-symlink paths;
- unique ZIP member names;
- safe two-component member paths under one Run ID;
- fixed ZIP timestamp, Unix regular-file mode, creator system, and stored compression;
- ZIP CRC;
- exact member coverage;
- canonical `PACKAGE_MANIFEST.json` bytes;
- package-manifest file sizes and SHA-256 values;
- package content-set SHA-256;
- internal `SHA256SUMS` syntax, uniqueness, coverage, and hashes;
- runtime `ARTIFACT_MANIFEST.json` coverage, sizes, and hashes;
- runtime Run ID, recorded directory name, and certification status;
- JSON readability of method and input evidence.

No statement is made about forecast accuracy, Hit@±1, MAE, MSE, RMSE, Holdout, or Prospective
performance.

## Result

Success returns JSON similar to:

```json
{
  "status": "VERIFIED",
  "formal_success": true,
  "run_id": "hierarchicalforecast-runtime-...",
  "certification_status": "VERIFIED",
  "zip_sha256": "...",
  "zip_member_count": 6
}
```

## Exit codes

| Exit | Meaning |
|---:|---|
| 0 | ZIP, sidecar, metadata, manifests, and all internal hashes verified |
| 2 | supplied evidence failed verification |
| 3 | verifier bootstrap or unexpected execution failure |

## Safety boundary

The verifier is read-only. It does not:

- create or replace a ZIP;
- create or replace a sidecar;
- extract files to disk;
- run HierarchicalForecast;
- trust a package solely because the sidecar matches;
- promote a pull request or runtime result.

A failed package must be preserved unchanged as incident evidence. Create a new runtime Run ID
rather than repairing or overwriting the transferred artifact.
