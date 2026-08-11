from types import ModuleType, SimpleNamespace

from loto.neuralforecast import db_training_evidence_facade as facade_install


def _facade_with_context(*, random_seed: int = 7, precision: str = "bf16-mixed"):
    context = SimpleNamespace(
        config=SimpleNamespace(random_seed=random_seed, precision=precision),
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
    return facade, core, context


def test_certification_bridge_injects_campaign_seed_and_precision() -> None:
    facade, core, _context = _facade_with_context()

    facade_install.install(facade)

    payload = core.certify_saved_runtime(require_gpu=True)
    assert payload["random_seed"] == 7
    assert payload["precision"] == "bf16-mixed"
    assert payload["require_gpu"] is True


def test_certification_bridge_preserves_explicit_values() -> None:
    facade, core, _context = _facade_with_context()

    facade_install.install(facade)

    payload = core.certify_saved_runtime(random_seed=99, precision="64-true")
    assert payload["random_seed"] == 99
    assert payload["precision"] == "64-true"


def test_certification_bridge_uses_resolved_plan_controls() -> None:
    facade, core, _context = _facade_with_context(random_seed=7, precision="bf16-mixed")
    facade_install.install(facade)

    plan = SimpleNamespace(
        precision="32-true",
        config={"random_seed": 11, "precision": "32-true"},
    )
    facade_install._record_resolved_certification_parameters(facade, plan=plan)

    payload = core.certify_saved_runtime()
    assert payload["random_seed"] == 11
    assert payload["precision"] == "32-true"


def test_certification_bridge_install_is_idempotent() -> None:
    facade, core, _context = _facade_with_context()

    facade_install.install(facade)
    first_wrapper = core.certify_saved_runtime
    facade_install.install(facade)

    assert core.certify_saved_runtime is first_wrapper
    assert core._loto_certification_parameter_bridge_installed is True
    payload = core.certify_saved_runtime(require_gpu=True)
    assert payload == {
        "require_gpu": True,
        "random_seed": 7,
        "precision": "bf16-mixed",
    }
