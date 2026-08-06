from __future__ import annotations

from typing import Any

import pytest

from loto.neuralforecast.auto_scinet import runtime


def test_dependency_status_is_explicit() -> None:
    status = runtime.runtime_dependency_status()
    assert set(status) == {"neuralforecast", "optuna", "ray", "torch"}
    assert all(isinstance(value, bool) for value in status.values())


def test_missing_dependencies_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runtime,
        "runtime_dependency_status",
        lambda: {
            "neuralforecast": False,
            "optuna": False,
            "ray": False,
            "torch": True,
        },
    )
    runtime._reset_runtime_classes_for_tests()
    with pytest.raises(runtime.RuntimeDependencyError, match="neuralforecast"):
        runtime.get_scinet_class()


def test_runtime_accessors_delegate_to_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    class Dummy:
        pass

    calls: list[int] = []

    def fake_build() -> tuple[type[Any], type[Any]]:
        calls.append(1)
        return Dummy, Dummy

    runtime._reset_runtime_classes_for_tests()
    monkeypatch.setattr(runtime, "_build_runtime_classes", fake_build)
    assert runtime.get_scinet_class() is Dummy
    assert runtime.get_auto_scinet_class() is Dummy
    assert len(calls) == 2
