from __future__ import annotations


def test_public_package_imports_without_optional_runtime_dependencies() -> None:
    import loto.run_lifecycle as lifecycle

    assert lifecycle.RunPhase.PLAN.value == "PLAN"
    assert lifecycle.RunStatus.PENDING.value == "PENDING"
    assert lifecycle.TRANSITION_RULES
