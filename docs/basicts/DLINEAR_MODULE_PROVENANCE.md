# BasicTS DLinear module provenance

Status: `LOCAL_CONTRACT_PASS / TARGET_HOST_EVIDENCE_PENDING`

The root `basicts` package provenance does not by itself prove that the concrete DLinear
implementation and configuration modules come from the same installed distribution. A shadowed
submodule could otherwise be selected after the root package identity check.

## Frozen module contract

The DLinear CPU smoke requires exactly these distribution entries and Python modules:

| Label | Distribution entry | Python module | Required symbol |
|---|---|---|---|
| `dlinear_arch` | `basicts/models/DLinear/arch/dlinear_arch.py` | `basicts.models.DLinear.arch.dlinear_arch` | `DLinear` |
| `dlinear_config` | `basicts/models/DLinear/config/dlinear_config.py` | `basicts.models.DLinear.config.dlinear_config` | `DLinearConfig` |

For each module, PASS requires:

- exactly one matching file in the installed `BasicTS` distribution manifest;
- a regular file located inside the distribution root;
- no symbolic link in the path from the distribution root to the file;
- RECORD hash mode `sha256`;
- exact URL-safe Base64 RECORD digest and byte-size agreement;
- `importlib.util.find_spec()` origin equal to the distribution-located file;
- a non-package module specification;
- any preloaded module `__file__` equal to the same file;
- the loaded module `__file__` equal to the same file;
- the required class present and defined by the expected module;
- a retained hexadecimal SHA-256 of the module file.

The frozen upstream revision contains both files under the corresponding `src/basicts/...` paths.
The installed distribution paths omit the repository's `src/` prefix because BasicTS uses a
setuptools `src` layout.

## Retained DLinear smoke evidence

`core/dlinear_smoke/response.json` and `DLINEAR_SMOKE.json` must contain:

```text
dlinear_module_provenance_status=PASS
dlinear_runtime_modules=[...exactly two entries...]
```

Each entry retains:

- `label`;
- `module_name`;
- `required_symbol` and `symbol_module`;
- `distribution_entry` and absolute `distribution_path`;
- `import_spec_origin` and `loaded_module_file`;
- `record_status`, `record_hash_mode`, `record_hash_value`, and `record_size_bytes`;
- `module_file_sha256`;
- `module_already_loaded`.

The runtime independently checks the overall status, exact module-name set, and the `__module__`
values of `DLinear` and `DLinearConfig` before training starts.

## Certificate requirement

The P0 certificate independently validates the complete two-module evidence set and must record:

```text
certified.dlinear_module_origin_bound_to_distribution=true
```

A valid identity bundle is insufficient when the DLinear module evidence is missing or invalid.

## Target-host review

After formal P0 succeeds:

```bash
RUN_DIR="artifacts/basicts/formal-p0/<RUN_ID>"

(
  cd "${RUN_DIR}/core/dlinear_smoke"
  sha256sum -c SHA256SUMS
  python -m json.tool response.json
  python -m json.tool DLINEAR_SMOKE.json
)
```

Review the compact module fields without changing the evidence bundle:

```bash
python - "${RUN_DIR}/core/dlinear_smoke/response.json" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evidence = response["evidence"]
print("status=", evidence["dlinear_module_provenance_status"])
for item in evidence["dlinear_runtime_modules"]:
    print(json.dumps(item, ensure_ascii=False, sort_keys=True))
PY
```

## Failure policy

Treat all of the following as formal failures:

- missing, duplicate, or unexpected DLinear distribution entries;
- missing or mismatched RECORD hash or size;
- a module path outside the distribution root;
- a symlinked path;
- a shadowed import specification or preloaded module;
- a loaded module file differing from the distribution file;
- a missing required class or a class defined by another module;
- retained evidence or certificate disagreement.

Import success, model construction, or finite predictions do not override a provenance failure.
