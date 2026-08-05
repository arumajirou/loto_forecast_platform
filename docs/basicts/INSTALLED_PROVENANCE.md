# BasicTS installed-distribution provenance

Status: `LOCAL_CONTRACT_PASS / TARGET_HOST_EVIDENCE_PENDING`

The environment revision variable and `uv.lock` describe intended inputs. They do not prove that the
Python distribution loaded at runtime came from that Git commit. The provider therefore verifies
installed metadata before every supported operation.

## Specification basis

Python packaging records direct URL installations in `direct_url.json` under the installed
`*.dist-info` directory:

- https://packaging.python.org/en/latest/specifications/direct-url/
- https://docs.python.org/3.11/library/importlib.metadata.html

The provider reads `direct_url.json` with
`importlib.metadata.distribution("BasicTS").read_text(...)` from the same distribution search path.

## Frozen contract

PASS requires all of the following:

- distribution metadata name: `BasicTS`;
- distribution version: `1.1.0`;
- direct URL repository: `https://github.com/GestaltCogTeam/BasicTS`;
- VCS: `git`;
- commit ID: `c2bb6e31e591167e84459775a21a62e70a5893ce`;
- requested revision: `c2bb6e31e591167e84459775a21a62e70a5893ce`;
- no `dir_info`, `archive_info`, or `subdirectory` substitution.

The normalizer accepts the expected repository URL with an optional trailing `.git` or slash. It
rejects credentials, query strings, fragments, ports, non-HTTPS schemes, other hosts, and other
repository paths.

## Retained identity evidence

`core/identity/response.json` must contain:

- `installed_provenance_status=PASS`;
- `distribution_name`;
- `distribution_version`;
- `direct_url_repository`;
- `direct_url_vcs`;
- `direct_url_commit_id`;
- `direct_url_requested_revision`;
- `direct_url_sha256`.

The raw metadata text is not copied because a direct URL can contain sensitive information. Its
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
):
    print(f"{field}={evidence[field]}")
PY
```

The P0 certificate must set `certified.installed_package_git_provenance=true`. Independent formal
verification re-runs the identity bundle verifier, so missing or changed installed provenance also
invalidates the later deterministic receipt.

## Failure policy

Treat any of the following as a formal failure:

- missing or malformed `direct_url.json`;
- registry, archive, editable, or local-directory installation;
- wrong distribution name or version;
- wrong repository, VCS, commit, or requested revision;
- mismatch between version APIs and provenance metadata;
- identity response, manifest, or SHA-256 disagreement.

Do not replace installed provenance with the launcher environment variable, lockfile text, package
version, import success, or a model inference result. Those are separate evidence layers.
