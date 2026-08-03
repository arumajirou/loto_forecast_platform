from __future__ import annotations

import numpy as np

from loto.probabilistic.catalog import list_probabilistic_model_specs
from loto.probabilistic.compatibility import compatible_task
from loto.probabilistic.config import load_run_config
from loto.probabilistic.dataset import synthetic_dataset, task_arrays
from loto.probabilistic.models.reference import fit_reference, posterior_draws


def test_all_72_models_fit_and_draw_on_a_compatible_geometry() -> None:
    config = load_run_config("configs/probabilistic/smoke.yaml")
    bundles = {
        "numbers3": synthetic_dataset("numbers3", rows=90, seed=1),
        "loto7": synthetic_dataset("loto7", rows=90, seed=2),
    }
    fitted = 0
    for spec in list_probabilistic_model_specs():
        selected = None
        for game in ("numbers3", "loto7"):
            task = compatible_task(spec, bundles[game].geometry)
            if task is not None:
                selected = (bundles[game], task)
                if spec.family == "count" and game == "numbers3":
                    continue
                break
        assert selected is not None, spec.model_id
        bundle, task = selected
        y, classes = task_arrays(bundle, task)
        posterior = fit_reference(
            spec,
            y=y[:80],
            classes=classes,
            target_mode=task,
            geometry=bundle.geometry,
            config=config,
            seed=42,
        )
        draws = posterior_draws(posterior, draws=32, seed=42)
        assert draws.shape[0] == 32
        assert np.isfinite(draws).all()
        assert np.allclose(draws.sum(axis=-1), 1.0)
        fitted += 1
    assert fitted == 72
