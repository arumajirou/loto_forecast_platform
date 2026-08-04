from __future__ import annotations

import copy
import json
from pathlib import Path

SOURCE = Path("configs/generated/neuralforecast_normalized_fair_spaces.json")

OUTPUT = Path("configs/generated/neuralforecast_normalized_fixed_seed_spaces.json")

SEARCH_SEED = 42
FORMAL_EVALUATION_SEEDS = [42, 123, 2026]


data = json.loads(SOURCE.read_text(encoding="utf-8"))

fixed = copy.deepcopy(data)

fixed["metadata"]["purpose"] = "Backend-neutral fair comparison space with fixed search seed"
fixed["metadata"]["search_seed_policy"] = "random_seed is fixed during hyperparameter search"
fixed["metadata"]["search_seed"] = SEARCH_SEED
fixed["metadata"]["formal_evaluation_seeds"] = FORMAL_EVALUATION_SEEDS

changed = []

for model, model_spec in fixed["models"].items():
    parameters = model_spec["parameters"]

    previous = parameters.get("random_seed")

    parameters["random_seed"] = {
        "kind": "fixed",
        "value": SEARCH_SEED,
        "purpose": "hyperparameter_search_reproducibility",
    }

    changed.append(
        {
            "model": model,
            "previous": previous,
            "fixed": SEARCH_SEED,
        }
    )

fixed["normalization_report"] = {
    "fixed_seed_models": len(changed),
    "search_seed": SEARCH_SEED,
    "formal_evaluation_seeds": FORMAL_EVALUATION_SEEDS,
}

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

OUTPUT.write_text(
    json.dumps(
        fixed,
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print("models=", len(fixed["models"]))
print("fixed_seed_models=", len(changed))
print("search_seed=", SEARCH_SEED)
print(
    "formal_evaluation_seeds=",
    FORMAL_EVALUATION_SEEDS,
)
print("OUT=", OUTPUT)
print("NORMALIZED_FIXED_SEED_SPACES=PASS")
