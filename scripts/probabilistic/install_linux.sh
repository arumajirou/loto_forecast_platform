#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
MODE="${PPL_INSTALL_MODE:-reference}"
LOG_DIR="${ROOT}/artifacts/install/probabilistic-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${LOG_DIR}"
exec > >(tee "${LOG_DIR}/install.log") 2>&1

cd "${ROOT}"
echo "ROOT=${ROOT}"
echo "MODE=${MODE}"
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv is required"; exit 2; }

case "${MODE}" in
  reference|native|all|pymc|jax|pyro|stan|tfp) ;;
  *) echo "ERROR: unsupported PPL_INSTALL_MODE=${MODE}"; exit 2 ;;
esac

uv sync --frozen --extra dev

case "${MODE}" in
  native)
    # One resolver transaction prevents sequential backend installs from replacing
    # ArviZ/JAX/PyTensor versions selected by a previous backend.
    uv pip install -r requirements-probabilistic-native.txt
    ;;
  all)
    uv pip install -r requirements-probabilistic-native.txt
    uv pip install -r requirements-probabilistic-stan.txt
    # TFP is an optional exhaustive cross-backend path, not a 72-primary-path dependency.
    uv pip install -r requirements-probabilistic-tfp.txt || true
    ;;
  pymc)
    uv pip install -r requirements-probabilistic-pymc.txt
    ;;
  jax)
    uv pip install -r requirements-probabilistic-jax.txt
    ;;
  pyro)
    uv pip install -r requirements-probabilistic-pyro.txt
    ;;
  stan)
    uv pip install -r requirements-probabilistic-stan.txt
    ;;
  tfp)
    uv pip install -r requirements-probabilistic-tfp.txt
    ;;
esac

uv run loto3 probabilistic catalog-list > "${LOG_DIR}/catalog.json"
uv run loto3 probabilistic native-coverage > "${LOG_DIR}/native-coverage.json"
uv run loto3 probabilistic backends > "${LOG_DIR}/backends.json"

if [[ "${MODE}" == "native" || "${MODE}" == "all" ]]; then
  uv run loto3 probabilistic validate-config \
    --config configs/probabilistic/native_smoke.yaml \
    > "${LOG_DIR}/config-validation.json"
  uv run python tools/verify_native_ppl_implementation.py \
    --root "${ROOT}" \
    --require-runtime \
    --output "${LOG_DIR}/native-verification.json"
else
  uv run loto3 probabilistic validate-config \
    --config configs/probabilistic/smoke.yaml \
    > "${LOG_DIR}/config-validation.json"
  uv run python tools/verify_native_ppl_implementation.py \
    --root "${ROOT}" \
    --output "${LOG_DIR}/native-static-verification.json"
fi

echo "INSTALL_STATUS=PASS"
echo "LOG_DIR=${LOG_DIR}"
