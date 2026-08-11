from types import ModuleType, SimpleNamespace

from loto.neuralforecast import db_training_evidence_facade as facade_install


def test_certification_bridge_injects_campaign_seed_and_precision() -> None:
    context = SimpleNamespace(
        config=SimpleNamespace(random_seed=7, precision="bf16-mixed"),
        spec=SimpleNamespace(model_id="nf-auto-dlinear"),
    )

    core = ModuleType("fake_core")
    core._construct_auto_hint = lambda config, panel: (config, panel)
    core.certify_saved_runtime = lambda *args, **kwargs: kwargs

    facade = ModuleType("fake_facade")
    facade._CORE = core
    facade._CONTEXT = SimpleNamespace(get=lambda: context)
    facade._construct_interceptor = lambda plan: plan
    facade._construct_auto_hint = lambda config, panel: (config, panel)

    facade_install.install(facade)

    payload = core.certify_saved_runtime(require_gpu=True)
    assert payload["random_seed"] == 7
    assert payload["precision"] == "bf16-mixed"
    assert payload["require_gpu"] is True


def test_certification_bridge_preserves_explicit_values() -> None:
    context = SimpleNamespace(
        config=SimpleNamespace(random_seed=7, precision="bf16-mixed"),
        spec=SimpleNamespace(model_id="nf-auto-dlinear"),
    )

    core = ModuleType("fake_core_explicit")
    core._construct_auto_hint = lambda config, panel: (config, panel)
    core.certify_saved_runtime = lambda *args, **kwargs: kwargs

    facade = ModuleType("fake_facade_explicit")
    facade._CORE = core
    facade._CONTEXT = SimpleNamespace(get=lambda: context)
    facade._construct_interceptor = lambda plan: plan
    facade._construct_auto_hint = lambda config, panel: (config, panel)

    facade_install.install(facade)

    payload = core.certify_saved_runtime(random_seed=99, precision="64-true")
    assert payload["random_seed"] == 99
    assert payload["precision"] == "64-true"
