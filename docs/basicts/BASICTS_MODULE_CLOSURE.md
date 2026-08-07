# BasicTS loaded module closure provenance

Status: `LOCAL_CONTRACT_PASS / TARGET_HOST_EVIDENCE_PENDING`

Verifying only `basicts/__init__.py`, `DLinear`, and `DLinearConfig` is not sufficient. Importing
DLinear also executes the BasicTS launcher, package initializers, configuration modules, and the
moving-average decomposition dependency. Any loaded `basicts.*` module outside the installed
BasicTS distribution could change behavior before training or inference.

## Closure boundary

The DLinear provider starts in a fresh subprocess. Before the first BasicTS import, PASS requires:

```text
preloaded_basicts_modules=[]
```

After the DLinear implementation and configuration modules are imported, the provider enumerates
every entry in `sys.modules` whose name is either `basicts` or begins with `basicts.`. This exact set
is the loaded BasicTS module closure for the run.

Every loaded module must provide a regular `__file__`. Namespace-only or memory-only BasicTS
modules are rejected by this contract.

## Distribution and RECORD requirements

For every loaded module, PASS requires:

- the loaded file is inside the installed BasicTS distribution root;
- no path component from the distribution root to the module file is a symbolic link;
- the relative file path appears exactly once in the distribution file manifest;
- `Distribution.locate_file()` resolves to the same regular file;
- the RECORD hash algorithm is `sha256`;
- the URL-safe Base64 RECORD digest matches the installed file bytes;
- the RECORD byte size matches the installed file size;
- `importlib.util.find_spec()` resolves to the same file;
- the loaded module `__file__`, import-spec origin, and distribution path are identical;
- the hexadecimal SHA-256 of the module file is retained;
- package versus non-package status is retained.

The closure evidence rejects duplicate module names and duplicate distribution entries.

## Runtime-critical modules

The complete closure can contain more modules depending on the frozen BasicTS import graph. At a
minimum, it must include:

```text
basicts.models.DLinear.arch.dlinear_arch
basicts.models.DLinear.config.dlinear_config
basicts.modules.decomposition
basicts.configs
basicts.configs.model_config
```

The exact installed closure, rather than a hard-coded total count, is retained. The recorded count
must exactly equal the retained list length.

## Dependency object binding

File provenance alone does not prove that the objects referenced by DLinear are the objects exported
by those verified files. PASS additionally requires:

- `dlinear_arch.MovingAverageDecomposition` is the same object as
  `basicts.modules.decomposition.MovingAverageDecomposition`;
- `dlinear_config.BasicTSModelConfig` is the same object as
  `basicts.configs.model_config.BasicTSModelConfig`;
- `basicts.configs.BasicTSModelConfig` exports that same object;
- `DLinearConfig` directly inherits that exact verified `BasicTSModelConfig` object;
- all relevant class `__module__` values match the frozen module contract.

The evidence records:

```text
dlinear_dependency_binding_status=PASS
dlinear_dependency_bindings.arch_decomposition_object_identity=true
dlinear_dependency_bindings.config_model_config_object_identity=true
dlinear_dependency_bindings.configs_export_object_identity=true
dlinear_dependency_bindings.dlinear_config_direct_base_identity=true
```

## Retained evidence

`core/dlinear_smoke/response.json` and `DLINEAR_SMOKE.json` must contain:

```text
basicts_module_closure_status=PASS
preloaded_basicts_modules=[]
loaded_basicts_module_count=<positive integer>
loaded_basicts_modules=<exact complete list>
dlinear_dependency_binding_status=PASS
dlinear_dependency_bindings=<exact binding record>
```

Each `loaded_basicts_modules` entry retains:

- `module_name`;
- `distribution_entry`;
- `distribution_path`;
- `import_spec_origin`;
- `loaded_module_file`;
- `record_status`;
- `record_hash_mode`;
- `record_hash_value`;
- `record_size_bytes`;
- `module_file_sha256`;
- `is_package`.

## Certificate requirements

The P0 certificate independently revalidates the complete closure and dependency-binding evidence.
It must record:

```text
certified.basicts_loaded_module_closure_bound_to_distribution=true
certified.dlinear_dependency_object_binding=true
```

These are additional to the root distribution and two DLinear-file certification flags.

## Target-host review

After formal P0 succeeds:

```bash
RUN_DIR="artifacts/basicts/formal-p0/<RUN_ID>"
RESPONSE="${RUN_DIR}/core/dlinear_smoke/response.json"

(
  cd "${RUN_DIR}/core/dlinear_smoke"
  sha256sum -c SHA256SUMS
)

python - "${RESPONSE}" <<'PY'
import json
import sys
from pathlib import Path

response = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evidence = response["evidence"]
print("closure_status=", evidence["basicts_module_closure_status"])
print("preloaded=", evidence["preloaded_basicts_modules"])
print("count=", evidence["loaded_basicts_module_count"])
for item in evidence["loaded_basicts_modules"]:
    print(json.dumps(item, ensure_ascii=False, sort_keys=True))
print(json.dumps(evidence["dlinear_dependency_bindings"], sort_keys=True))
PY
```

Review that the count equals the printed module-entry count, all files are under the expected
isolated environment, all RECORD fields report PASS, and no unexpected source tree or `PYTHONPATH`
location appears.

## Failure policy

Treat any of the following as a formal failure:

- any preloaded BasicTS module;
- missing or non-file module origin;
- a module outside the distribution root;
- any symlink in a module path;
- missing, duplicated, or mismatched distribution entry;
- missing or mismatched RECORD SHA-256 or byte size;
- import-spec, loaded-file, and distribution-path disagreement;
- duplicate module names or file entries;
- missing runtime-critical modules;
- closure count disagreement;
- dependency object or direct-base identity disagreement;
- runtime response, manifest, certificate, independent verification, or receipt disagreement.

Successful import, finite predictions, or save/load equality do not override a closure provenance
failure.
