# BasicTS installed-distribution and import-origin provenance

Status: `LOCAL_CONTRACT_PASS / TARGET_HOST_EVIDENCE_PENDING`

The environment revision variable and `uv.lock` describe intended inputs. `direct_url.json` proves
which source produced an installed distribution, but it does not by itself prove that Python will
import modules from that distribution. A local `basicts/` directory or an earlier `PYTHONPATH`
entry could otherwise shadow the verified installation.

The provider therefore verifies both the installed distribution and the actual import resolution
before every supported operation.

## Specification basis

Python packaging records direct URL installations in `direct_url.json` under the installed
`*.dist-info` directory. Python also exposes distribution files, import-to-distribution mappings,
and module specifications through `importlib.metadata` and `importlib.util`:

- https://packaging.python.org/en/latest/specifications/direct-url/
- https://docs.python.org/3.11/library/importlib.metadata.html
- https://docs.python.org/3.11/library/importlib.html#importlib.util.find_spec

The provider reads metadata and import resolution from the same Python process used by the BasicTS
provider.

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

## Import-origin binding contract

The installed distribution must expose exactly one `basicts/__init__.py` entry in its distribution
file manifest. The provider then requires:

- `importlib.metadata.packages_distributions()["basicts"] == ["BasicTS"]`;
- `importlib.util.find_spec("basicts")` resolves to a filesystem package;
- the resolved import origin exactly equals the distribution-located `basicts/__init__.py`;
- the package search location is exactly the parent directory of that file;
- neither the package directory nor the import file is a symbolic link;
- if `basicts` is already loaded, its `__file__` resolves to the same distribution file.

The SHA-256 of the resolved `basicts/__init__.py` is retained. This binds the runtime identity
record to the concrete package file that Python would import.

## Retained identity evidence

`core/identity/response.json` must contain the direct-install fields:

- `installed_provenance_status=PASS`;
- `distribution_name` and `distribution_version`;
- `direct_url_repository`, `direct_url_vcs`, `direct_url_commit_id`;
- `direct_url_requested_revision` and `direct_url_sha256`.

It must also contain the import-origin fields:

- `import_origin_status=PASS`;
- `import_name=basicts`;
- `import_provider_distributions=["BasicTS"]`;
- `distribution_package_entry=basicts/__init__.py`;
- `distribution_package_init` and `import_spec_origin` with identical values;
- `import_submodule_search_locations`;
- `import_origin_sha256`;
- `module_already_loaded`.

The raw direct URL metadata is not copied because it can contain sensitive information. Its
SHA-256 is retained so the exact text consumed by the runtime can be compared without exposing it.

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
    "distribution_name",
    "distribution_version",
    "direct_url_repository",
    "direct_url_vcs",
    "direct_url_commit_id",
    "direct_url_requested_revision",
    "direct_url_sha256",
    "import_origin_status",
    "import_name",
    "import_provider_distributions",
    "distribution_package_entry",
    "distribution_package_init",
    "import_spec_origin",
    "import_submodule_search_locations",
    "import_origin_sha256",
    "module_already_loaded",
):
    print(f"{field}={evidence[field]}")
PY
```

The P0 certificate must set both:

```text
certified.installed_package_git_provenance=true
certified.import_origin_bound_to_distribution=true
```

Independent formal verification re-runs the identity bundle verifier. Missing or changed import
origin evidence therefore also invalidates the later deterministic receipt.

## Failure policy

Treat any of the following as a formal failure:

- missing or malformed `direct_url.json`;
- registry, archive, editable, or local-directory installation;
- wrong distribution name, version, repository, VCS, commit, or requested revision;
- missing or ambiguous distribution file manifest or import-provider mapping;
- `basicts` resolving outside the installed distribution;
- namespace-style or multiple package search locations;
- preloaded module origin drift;
- symlinked package or module origin;
- identity response, manifest, certificate, or SHA-256 disagreement.

Do not replace these checks with the launcher environment variable, lockfile text, package version,
import success, or a model inference result. Those are separate evidence layers.
