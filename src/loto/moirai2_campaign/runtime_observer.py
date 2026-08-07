from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ForwardDeviceEvidence:
    forward_call_count: int
    input_tensor_devices: tuple[str, ...]
    output_tensor_devices: tuple[str, ...]

    def as_dict(self) -> dict[str, int | list[str]]:
        payload = asdict(self)
        payload["input_tensor_devices"] = list(self.input_tensor_devices)
        payload["output_tensor_devices"] = list(self.output_tensor_devices)
        return payload


def _collect_tensor_devices(value: Any, output: set[str]) -> None:
    import torch

    if torch.is_tensor(value):
        output.add(str(value.device))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_tensor_devices(item, output)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_tensor_devices(item, output)


class ForwardDeviceObserver:
    """Capture devices observed at a torch module's public forward boundary."""

    def __init__(self) -> None:
        self._input_devices: set[str] = set()
        self._output_devices: set[str] = set()
        self._forward_call_count = 0
        self._handles: list[Any] = []

    def attach(self, module: Any) -> "ForwardDeviceObserver":
        if self._handles:
            raise RuntimeError("forward device observer is already attached")
        self._handles = [
            module.register_forward_pre_hook(self._pre_hook, with_kwargs=True),
            module.register_forward_hook(self._post_hook, with_kwargs=True),
        ]
        return self

    def _pre_hook(self, _module: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self._forward_call_count += 1
        _collect_tensor_devices(args, self._input_devices)
        _collect_tensor_devices(kwargs, self._input_devices)

    def _post_hook(
        self,
        _module: Any,
        _args: tuple[Any, ...],
        _kwargs: dict[str, Any],
        output: Any,
    ) -> None:
        _collect_tensor_devices(output, self._output_devices)

    def close(self) -> None:
        for handle in self._handles:
            handle.remove()
        self._handles.clear()

    def evidence(self) -> ForwardDeviceEvidence:
        return ForwardDeviceEvidence(
            forward_call_count=self._forward_call_count,
            input_tensor_devices=tuple(sorted(self._input_devices)),
            output_tensor_devices=tuple(sorted(self._output_devices)),
        )
