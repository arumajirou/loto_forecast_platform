from __future__ import annotations

import torch
from torch import nn


class TinyLinearForecaster(nn.Module):
    """Minimal deterministic model used only for provider contract certification."""

    def __init__(self, input_len: int, output_len: int, channels: int) -> None:
        super().__init__()
        self.input_len = input_len
        self.output_len = output_len
        self.channels = channels
        self.projection = nn.Linear(input_len, output_len)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        if inputs.ndim != 4:
            raise ValueError("inputs must have shape [batch, time, channel, feature]")
        if inputs.shape[1] != self.input_len or inputs.shape[2] != self.channels:
            raise ValueError("input shape does not match configured geometry")
        values = inputs[..., 0].transpose(1, 2)
        forecast = self.projection(values).transpose(1, 2)
        return forecast.unsqueeze(-1)
