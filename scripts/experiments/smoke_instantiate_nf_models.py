from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import neuralforecast.models as models
from neuralforecast.losses.pytorch import MAE

SPACE_SOURCE = Path("configs/generated/neuralforecast_normalized_fixed_seed_spaces.json")

MATRIX_SOURCE = Path("artifacts/parameter_inventory/neuralforecast_auto_model_matrix_v2.json")

OUTPUT = Path("artifacts/runtime_certification/neuralforecast_model_instantiation_smoke.json")


def resolve_value(
    spec: dict[str, Any],
) -> Any:
    kind = spec["kind"]

    if kind == "fixed":
        return spec["value"]

    if kind == "categorical":
        return spec["values"][0]

    if kind in {
        "float",
        "log_float",
        "discrete_float",
        "integer",
        "log_int",
    }:
        return spec["lower"]

    raise ValueError(f"Unsupported kind {kind!r}")


spaces = json.loads(SPACE_SOURCE.read_text(encoding="utf-8"))

matrix = json.loads(MATRIX_SOURCE.read_text(encoding="utf-8"))

matrix_by_auto = {record["auto_model"]: record for record in matrix}

results = []

for auto_name, model_space in spaces["models"].items():
    matrix_record = matrix_by_auto[auto_name]
    base_name = matrix_record["base_model"]
    model_cls = getattr(models, base_name)

    signature = inspect.signature(model_cls.__init__)

    accepted = set(signature.parameters) - {"self"}

    candidate = {name: resolve_value(spec) for name, spec in model_space["parameters"].items()}

    candidate.update(
        {
            "h": 1,
            "loss": MAE(),
            "valid_loss": MAE(),
            "alias": (f"smoke_{base_name}"),
        }
    )

    # Do not pass tuning-only or unsupported keys.
    config = {key: value for key, value in candidate.items() if key in accepted}

    # Keep constructor certification inexpensive.
    if "max_steps" in config:
        config["max_steps"] = 1

    if "input_size" in config:
        current = config["input_size"]

        # Do not rely on the BaseModel automatic fallback
        # from -1 to 3 * horizon during certification.
        if current == -1:
            config["input_size"] = 3

        if "inference_input_size" in config and config["inference_input_size"] == -1:
            config["inference_input_size"] = int(config["input_size"])

        # Encoder-decoder Transformer models require enough
        # context for decoder_input_size_multiplier=0.5.
        if base_name in {
            "Autoformer",
            "FEDformer",
            "Informer",
            "VanillaTransformer",
        }:
            config["input_size"] = max(
                int(config["input_size"]),
                4,
            )

        # PatchTST needs context at least as long as a patch.
        if base_name == "PatchTST":
            patch_len = int(config.get("patch_len", 16))
            config["input_size"] = max(
                int(config["input_size"]),
                patch_len,
            )

    # The default N-BEATS trend/seasonality stacks are not
    # valid for a one-step horizon. Certify the identity stack.
    if base_name in {
        "NBEATS",
        "NBEATSx",
    }:
        config["stack_types"] = ["identity"]
        config["n_blocks"] = [1]
        config["mlp_units"] = [[64, 64]]

    try:
        instance = model_cls(**config)

        results.append(
            {
                "auto_model": auto_name,
                "base_model": base_name,
                "status": "PASS",
                "instance_class": (type(instance).__name__),
                "config": config,
            }
        )

        print(
            f"{auto_name:28s}",
            f"{base_name:24s}",
            "PASS",
        )

    except Exception as exc:
        error_text = repr(exc)

        status = (
            "OPTIONAL_DEPENDENCY_MISSING"
            if (base_name == "xLSTM" and "Please install `xlstm`" in error_text)
            else "ERROR"
        )

        results.append(
            {
                "auto_model": auto_name,
                "base_model": base_name,
                "status": status,
                "error": error_text,
                "config": config,
            }
        )

        print(
            f"{auto_name:28s}",
            f"{base_name:24s}",
            status,
            error_text,
        )


OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    json.dumps(
        results,
        indent=2,
        ensure_ascii=False,
        default=repr,
    ),
    encoding="utf-8",
)

passed = sum(record["status"] == "PASS" for record in results)

optional_missing = sum(record["status"] == "OPTIONAL_DEPENDENCY_MISSING" for record in results)

failed = sum(record["status"] == "ERROR" for record in results)

print("models=", len(results))
print("passed=", passed)
print(
    "optional_dependency_missing=",
    optional_missing,
)
print("failed=", failed)
print("OUT=", OUTPUT)

if failed:
    print("NF_MODEL_INSTANTIATION_SMOKE=PARTIAL")
elif optional_missing:
    print("NF_MODEL_INSTANTIATION_SMOKE=PASS_WITH_OPTIONAL_MISSING")
else:
    print("NF_MODEL_INSTANTIATION_SMOKE=PASS")
