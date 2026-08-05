# BasicTS formal P0 runbook

Status: `TARGET_HOST_EXECUTION_PENDING`

This runbook executes the isolated BasicTS dependency audit and DLinear CPU certification without
modifying the root dependency graph or shared runtime paths.

## Frozen inputs

- repository: `GestaltCogTeam/BasicTS`
- package version: `1.1.0`
- upstream revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`
- Python lane: CPython 3.11
- uv version: `0.12.0`
- resolution cutoff: `2026-08-05T00:00:00Z`
- seed: `1`

`uv workspace metadata` currently exposes a preview JSON schema. The formal audit therefore pins
the uv version and stores the complete metadata JSON, canonical audit JSON, command logs, and
SHA-256 values. Do not substitute a different uv version without updating and reviewing the schema
contract and focused tests.

Installed-distribution provenance is a separate required layer. See
`docs/basicts/INSTALLED_PROVENANCE.md`. The environment revision marker and lockfile do not replace
verification of the installed distribution's `direct_url.json` or the actual `basicts` import
origin selected by Python.

## Preconditions

Run from a clean checkout of Draft PR #56 on a network-capable Linux host.

```bash
cd /mnt/e/env/ts/loto_forecast_platform || exit 1

git status --short
git rev-parse HEAD
uv --version
python --version
```

Required before execution:

- tracked repository files are clean;
- `uv --version` reports exactly `uv 0.12.0`;
- Python can start the repository module using `PYTHONPATH=${PWD}/src`;
- the host can reach the Python package and Git sources;
- the final Run ID does not already exist.

## Execute

```bash
set -Eeuo pipefail

cd /mnt/e/env/ts/loto_forecast_platform || exit 1

RUN_ID="basicts-formal-p0-$(date -u +%Y%m%d-%H%M%S)"
ARTIFACTS_ROOT="${PWD}/artifacts/basicts/formal-p0"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_orchestration \
  --repo-root "${PWD}" \
  --artifacts-root "${ARTIFACTS_ROOT}" \
  --run-id "${RUN_ID}" \
  --timeout-seconds 1800
```

The formal preflight performs one dependency resolution and one explicit frozen synchronization.
The nested core P0 validates the preflight lock SHA-256 and reuses that environment. It does not run
another `uv lock` or explicit `uv sync`. Every core `uv run` uses `--frozen`; uv may check or
synchronize the already prepared environment, but it cannot update the lockfile silently. The core
also verifies the lock SHA-256 again before certification.

Before identity, configuration, or DLinear can pass, the provider requires exact non-editable Git
provenance for the installed `BasicTS` distribution. It also binds Python's actual `basicts` import
spec to the distribution-located `basicts/__init__.py`, rejects ambiguous provider mappings and
shadow packages, and retains the imported file SHA-256.

The core status records one of these environment modes:

- `FORMAL_PREFLIGHT_REUSE`: dependency resolution came from the formal preflight;
- `STANDALONE_RESOLUTION`: the core was executed directly and performed its own lock and sync.

## Expected PASS output

The command must print both lines:

```text
BASICTS_FORMAL_P0_STATUS=PASS
RUN_DIR=<absolute path>
```

The final directory is published atomically only after dependency and runtime certification pass.
A failed run returns exit code `2` and retains a diagnostic bundle with `status=FAILED`.

## Independent verification

Run the read-only verifier after the formal command. Its report is deliberately written beside the
source bundle so the original recursive manifest and checksum set remain immutable.

```bash
RUN_DIR="${ARTIFACTS_ROOT}/${RUN_ID}"
VERIFY_REPORT="${ARTIFACTS_ROOT}/${RUN_ID}.verification.json"

PYTHONPATH="${PWD}/src" \
python -m loto.basicts_campaign.formal_verification \
  --run-dir "${RUN_DIR}" \
  --output "${VERIFY_REPORT}"

(
  cd "${ARTIFACTS_ROOT}"
  sha256sum -c "$(basename "${VERIFY_REPORT}").sha256"
)

python -m json.tool "${VERIFY_REPORT}"
```

The verifier fails closed on:

- symbolic links or unsafe relative paths;
- missing, duplicate, additional, or modified files;
- recursive manifest or SHA-256 disagreement;
- dependency metadata, uv version, Python lane, or package drift;
- missing command logs or an unexpected command phase order;
- non-frozen core model commands;
- formal, preflight, core, certificate, or lock SHA-256 cross-link disagreement;
- installed distribution repository, VCS, commit, or requested-revision disagreement;
- import-provider ambiguity, package-file drift, or import-origin shadowing;
- provider identity, allowlist, or DLinear evidence disagreement.

The following shell checks remain useful as an independent implementation of the checksum review:

```bash
(
  cd "${RUN_DIR}"
  sha256sum -c SHA256SUMS
  python -m json.tool FORMAL_P0_STATUS.json
  python -m json.tool FORMAL_P0_MANIFEST.json
  python -m json.tool preflight/UV_RESOLUTION_AUDIT.json
  python -m json.tool core/P0_RUN_STATUS.json
  python -m json.tool core/P0_CERTIFICATION_REPORT.json
  python -m json.tool core/identity/response.json
)

(
  cd "${RUN_DIR}/preflight"
  sha256sum -c UV_RESOLUTION_AUDIT.json.sha256
)

(
  cd "${RUN_DIR}/core"
  sha256sum -c SHA256SUMS
  sha256sum -c P0_CERTIFICATION_REPORT.json.sha256
)

(
  cd "${RUN_DIR}/core/identity"
  sha256sum -c SHA256SUMS
)
```

PASS requires the verifier and all checksum commands to succeed. The verification report, formal
status, dependency audit, core status, and core certificate must all report `PASS`. For a formal
run, `core/P0_RUN_STATUS.json` must record `environment_mode=FORMAL_PREFLIGHT_REUSE`.

The identity response must record the exact direct Git provenance and these import-origin fields:

```text
installed_provenance_status=PASS
import_origin_status=PASS
import_name=basicts
import_provider_distributions=["BasicTS"]
distribution_package_entry=basicts/__init__.py
distribution_package_init=<absolute installed file>
import_spec_origin=<same absolute installed file>
import_submodule_search_locations=[<installed basicts package directory>]
import_origin_sha256=<64 lowercase hexadecimal characters>
```

`distribution_package_init` and `import_spec_origin` must be identical. The certificate must set
both `certified.installed_package_git_provenance=true` and
`certified.import_origin_bound_to_distribution=true`.

The verification report certifies the retained evidence only. It does not rerun installation,
training, inference, or accuracy evaluation.

## Mandatory review before promotion

Review at least:

- exact Git commit in the core status;
- uv version and resolution cutoff;
- BasicTS lock and workspace-metadata source, version, and revision;
- installed BasicTS distribution name, version, repository, VCS, commit, and requested revision;
- SHA-256 of the raw installed `direct_url.json` consumed by the provider;
- exact import-to-distribution mapping for `basicts`;
- equality of distribution package file, import spec origin, and package search location;
- SHA-256 of the resolved `basicts/__init__.py`;
- whether `basicts` was already loaded and, if so, the verified loaded module origin;
- resolved versions of easy-torch, numpy, setuptools, torch, and transformers;
- CPython implementation and 3.11 version;
- absence of workspace conflicts;
- DLinear input, target, and prediction shapes;
- finite losses, model state, and predictions;
- CPU device and no CPU fallback claim;
- strict save/load and exact re-prediction equality;
- request SHA-256 and seed values;
- top-level and nested manifests.

After review, commit `environments/basicts-py311/uv.lock` normally. Do not force-push, rewrite
history, enable auto-merge, or promote the Draft PR solely because the formal P0 command returned
PASS.

## Failure handling

Use `FORMAL_P0_STATUS.json` and the recorded `failed_phase` first. Then inspect the matching files
under `preflight/logs/` or `core/logs/`. Do not repeatedly rerun an unchanged failure. Preserve the
failed bundle for comparison with the next Run ID.

A failure in dependency resolution, installed provenance, import-origin binding, identity, import
allowlisting, DLinear execution, persistence, re-prediction, finite-value checks, shape checks, or
SHA-256 verification is a formal failure. It must not be converted to PASS manually.
