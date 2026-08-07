from __future__ import annotations

import torch

from loto.moirai2_campaign.runtime_observer import ForwardDeviceObserver


def test_forward_device_observer_captures_cpu_inputs_and_outputs() -> None:
    module = torch.nn.Linear(3, 2)
    observer = ForwardDeviceObserver().attach(module)
    output = module(torch.ones(1, 3))
    assert output.shape == (1, 2)
    observer.close()
    evidence = observer.evidence()
    assert evidence.forward_call_count == 1
    assert evidence.input_tensor_devices == ("cpu",)
    assert evidence.output_tensor_devices == ("cpu",)


def test_forward_device_observer_rejects_double_attach() -> None:
    module = torch.nn.Identity()
    observer = ForwardDeviceObserver().attach(module)
    try:
        try:
            observer.attach(module)
        except RuntimeError as exc:
            assert "already attached" in str(exc)
        else:
            raise AssertionError("double attach was accepted")
    finally:
        observer.close()
