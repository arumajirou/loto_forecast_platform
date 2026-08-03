from __future__ import annotations

from loto.probabilistic.catalog import list_probabilistic_model_specs
from loto.probabilistic.config import load_run_config
from loto.probabilistic.models.numpyro_native import NUMPYRO_NATIVE_MODEL_IDS
from loto.probabilistic.models.pymc_native import PYMC_NATIVE_MODEL_IDS
from loto.probabilistic.models.pyro_native import PYRO_NATIVE_MODEL_IDS
from loto.probabilistic.native_registry import list_native_implementations, native_coverage
from loto.probabilistic.planner import build_plan


def test_all_models_have_one_primary_native_path() -> None:
    implementations = list_native_implementations()
    specs = {spec.model_id: spec for spec in list_probabilistic_model_specs()}
    assert len(implementations) == 74
    assert len({item.model_id for item in implementations}) == 74
    assert set(specs) == {item.model_id for item in implementations}
    for item in implementations:
        spec = specs[item.model_id]
        assert spec.primary_backend == item.primary_backend
        assert spec.primary_profile == item.primary_profile
        assert spec.native_graph_id == item.graph_id
        assert spec.native_implementation_status == "IMPLEMENTED"


def test_native_builder_dispatch_is_complete() -> None:
    implementations = list_native_implementations()
    expected = {
        "pymc": PYMC_NATIVE_MODEL_IDS,
        "numpyro": NUMPYRO_NATIVE_MODEL_IDS,
        "pyro": PYRO_NATIVE_MODEL_IDS,
        "pymc_bart": {"pp-bart-categorical"},
        "arviz": {"pp-psis-loo-stacking"},
        "builtin": {
            "pp-conditional-bernoulli-fixed-k",
            "pp-multinomial-dglm",
            "pp-uniform-dirichlet",
            "pp-static-dirichlet-categorical",
            "pp-expanding-dirichlet-categorical",
            "pp-rolling-dirichlet-categorical",
            "pp-discounted-dirichlet-categorical",
            "pp-posterior-utility-hit1",
            "pp-posterior-utility-hit1-mse",
            "pp-posterior-constrained-decoder",
        },
    }
    actual: dict[str, set[str]] = {}
    for item in implementations:
        actual.setdefault(item.primary_backend, set()).add(item.model_id)
    assert actual == expected
    assert sum(map(len, actual.values())) == 74


def test_native_full_plan_never_silently_adds_builtin() -> None:
    config = load_run_config("configs/probabilistic/native_smoke.yaml")
    trials = build_plan(config)
    assert len(trials) == 74
    implementation = {item.model_id: item for item in list_native_implementations()}
    for trial in trials:
        assert trial.backend == implementation[trial.model_id].primary_backend
        assert trial.inference_profile_id == implementation[trial.model_id].primary_profile


def test_native_coverage_counts() -> None:
    coverage = native_coverage()
    assert coverage["models"] == 74
    assert coverage["all_primary_paths_declared"] is True
    assert coverage["by_primary_backend"] == {
        "arviz": 1,
        "builtin": 10,
        "numpyro": 6,
        "pymc": 46,
        "pymc_bart": 1,
        "pyro": 10,
    }
