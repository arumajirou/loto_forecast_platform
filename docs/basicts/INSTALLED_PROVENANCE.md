# BasicTS installed-distribution, RECORD, and import-origin provenance

Status: `LOCAL_CONTRACT_PASS / TARGET_HOST_EVIDENCE_PENDING`

The environment revision variable and `uv.lock` describe intended inputs. `direct_url.json` proves
which source produced an installed distribution, but it does not by itself prove that the installed
files remain unchanged or that Python will import modules from that distribution. A local
`basicts/` directory, an earlier `PYTHONPATH` entry, or post-install file replacement could otherwise
bypass the intended runtime identity.

The provider therefore verifies the installed Git provenance, selected RECORD entries, and actual
import resolution before every supported operation.

## Specification basis

Python packaging records direct URL installations in `direct_url.json` under the installed
`*.dist-info` directory. The installed-project specification defines `RECORD` entries as a path,
optional content hash, and optional byte size. Python exposes those values through
`importlib.metadata.PackagePath.hash` and `.size`:

- https://packaging.python.org/en/latest/specifications/direct-url/
- https://packaging.python.org/en/latest/specifications/recording-installed-packages/
- https://docs.python.org/3.11/library/importlib.metadata.html
- https://docs.python.org/3.11/library/importlib.html#importlib.util.find_spec

The general packaging specification permits an installer to omit a RECORD hash or size. This
BasicTS contract is deliberately stricter: both values are mandatory for the two identity-critical
files described below. An installation that omits them remains usable by Python but is not formally
certifiable by this integration.

## Frozen distribution contract

PASS requires all of the following:

- distribution metadata name: `BasicTS`;
- distribution version: `1.1.0`;
- direct URL repository: `https://github.com/GestaltCogTeam/BasicTS`;
- VCS: `git`;
- commit ID: `c2bb6e31e591167e84459775a21a62e70a5893ce`;
- requested revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`;
- no `dir_info`, `archive_info`, or `subdirectory` substitution.

The URL normalizer accepts the expected repository with an optional trailing `.git` or slash. It
rejects credentials, query strings, fragments, ports, non-HTTPS schemes, other hosts, and other
repository paths.

## RECORD integrity contract

The distribution file manifest must contain exactly one entry for each of:

- `basicts/__init__.py`;
- `<distribution>.dist-info/direct_url.json`.

For both entries, PASS requires:

- a RECORD hash with algorithm `sha256`;
- a URL-safe Base64 digest without padding that exactly matches the installed file bytes;
- a non-empty integer RECORD size that exactly matches the file size;
- a regular, non-symlink file at the location resolved by the distribution metadata.

The text returned by `Distribution.read_text("direct_url.json")` must also exactly equal the content
of the RECORD-located `direct_url.json`. This prevents metadata lookup and installed-file lookup
from referring to different content.

## Import-origin binding contract

The provider requires:

- `importlib.metadata.packages_distributions()["basicts"] == ["BasicTS"]`;
- `importlib.util.find_spec("basicts")` resolves to a filesystem package;
- the resolved import origin exactly equals the distribution-located `basicts/__init__.py`;
- the package search location is exactly the parent directory of that file;
- neither the package directory nor the import file is a symbolic link;
- if `basicts` is already loaded, its `__file__` resolves to the same distribution file.

The hexadecimal SHA-256 of the resolved `basicts/__init__.py` is retained in addition to the
URL-safe Base64 RECORD digest. These are different encodings of the same SHA-256 algorithm and serve
different evidence layers.

## Retained identity evidence

`core/identity/response.json` must contain the direct-install fields:

- `installed_provenance_status=PASS`;
- `distribution_name` and `distribution_version`;
- `direct_url_repository`, `direct_url_vcs`, `direct_url_commit_id`;
- `direct_url_requested_revision` and `direct_url_sha256`.

It must contain the RECORD fields:

- `installed_record_integrity_status=PASS`;
- `direct_url_record_entry` and `direct_url_record_path`;
- `direct_url_record_status=PASS`;
- `direct_url_record_hash_mode=sha256`;
- `direct_url_record_hash_value` and `direct_url_record_size_bytes`;
- `package_init_record_status=PASS`;
- `package_init_record_hash_mode=sha256`;
- `package_init_record_hash_value` and `package_init_record_size_bytes`.

It must also contain the import-origin fields:

- `import_origin_status=PASS`;
- `import_name=basicts`;
- `import_provider_distributions=["BasicTS"]`;
- `distribution_package_entry=basicts/__init__.py`;
- `distribution_package_init` and `import_spec_origin` with identical values;
- `import_submodule_search_locations`;
- `import_origin_sha256`;
- `module_already_loaded`.

The raw direct URL metadata is not copied into a separate evidence file because it can contain
sensitive information. Its hexadecimal SHA-256 and its RECORD digest are retained so the exact
metadata consumed by the runtime can be compared without publishing the raw source URL again.

## Target-host review

After formal P0 succeeds, inspect the hashed identity response:

```bash
RUN_DIR="artifacts/basicts/formal-p0/<RUN_ID>"

(
  cd "${RUN_DIR}/core/identity"
  sha256sum -c SHA256SUMS
  python -m json.tool response.json
)
```

A compact field check can be run without changing the source bundle:

```bash
python - "${RUN_DIR}/core/identity/response.json" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evidence = response["evidence"]
for field in (
    "installed_provenance_status",
    "installed_record_integrity_status",
    "distribution_name",
    "distribution_version",
    "direct_url_repository",
    "direct_url_vcs",
    "direct_url_commit_id",
    "direct_url_requested_revision",
    "direct_url_sha256",
    "direct_url_record_entry",
    "direct_url_record_path",
    "direct_url_record_status",
    "direct_url_record_hash_mode",
    "direct_url_record_hash_value",
    "direct_url_record_size_bytes",
    "import_origin_status",
    "import_name",
    "import_provider_distributions",
    "distribution_package_entry",
    "distribution_package_init",
    "import_spec_origin",
    "import_submodule_search_locations",
    "import_origin_sha256",
    "module_already_loaded",
    "package_init_record_status",
    "package_init_record_hash_mode",
    "package_init_record_hash_value",
    "package_init_record_size_bytes",
):
    print(f"{field}={evidence[field]}")
PY
```

The P0 certificate must set all of:

```text
certified.installed_package_git_provenance=true
certified.installed_record_integrity=true
certified.import_origin_bound_to_distribution=true
```

Independent formal verification re-runs the identity bundle verifier. Missing or changed RECORD or
import-origin evidence therefore also invalidates the later deterministic receipt.

## Failure policy

Treat any of the following as a formal failure:

- missing or malformed `direct_url.json`;
- registry, archive, editable, or local-directory installation;
- wrong distribution name, version, repository, VCS, commit, or requested revision;
- missing or ambiguous distribution file manifest or import-provider mapping;
- missing, unsupported, or mismatched RECORD hash or size;
- disagreement between `Distribution.read_text()` and the RECORD-located metadata file;
- `basicts` resolving outside the installed distribution;
- namespace-style or multiple package search locations;
- preloaded module origin drift;
- symlinked package, metadata file, or module origin;
- identity response, manifest, certificate, or SHA-256 disagreement.

Do not replace these checks with the launcher environment variable, lockfile text, package version,
import success, or a model inference result. Those are separate evidence layers.
