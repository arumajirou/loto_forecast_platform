# Phase 3B Venv Identity Audit

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- corrected identity method: `sys.prefix`
- raw Python interpreter paths: 52
- distinct sys.prefix identities: 20
- virtual environments: 20
- base interpreters: 0

## Environment mapping

- `DIRECT_PROJECT_RUNTIME`: 10
- `EXISTING_VENV_CANDIDATE`: 7
- `MULTIPLE_VENV_CANDIDATES`: 2
- `UNRESOLVED_NO_RUNTIME`: 10

## Remaining

- unresolved source environments: 10
- environments with multiple candidates: 2
- TimesFM runtime identities: 1

## Phase 3 correction

Phase 3 used the realpath of the Python interpreter. Independent uv virtual environments can share the same base interpreter, so this collapses separate site-packages environments.

Phase 3B uses `sys.prefix`. Separate venvs therefore remain separate even when their Python executable ultimately points to the same uv-managed interpreter.

## Certification boundary

No model checkpoint was loaded. No model forecast or formal runtime certification was performed.
