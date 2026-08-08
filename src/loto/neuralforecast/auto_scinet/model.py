"""NeuralForecast SCINet class factory."""

from __future__ import annotations

from typing import Any

from .contracts import resolve_architecture, resolve_training


def build_scinet_class(
    *,
    base_model: type[Any],
    functional: Any,
    losses: Any,
    nn: Any,
    torch: Any,
    module_name: str,
) -> type[Any]:
    class Splitting(nn.Module):
        def forward(self, values: Any) -> tuple[Any, Any]:
            return values[:, ::2, :], values[:, 1::2, :]

    class CausalConvBlock(nn.Module):
        def __init__(self, d_model: int, kernel_size: int = 5) -> None:
            super().__init__()
            self.causal_conv = nn.Sequential(
                nn.ReplicationPad1d((kernel_size - 1, kernel_size - 1)),
                nn.Conv1d(d_model, d_model, kernel_size=kernel_size),
                nn.LeakyReLU(negative_slope=0.01, inplace=True),
                nn.Dropout(0.0),
                nn.Conv1d(d_model, d_model, kernel_size=kernel_size),
                nn.Tanh(),
            )

        def forward(self, values: Any) -> Any:
            return self.causal_conv(values)

    class SCIBlock(nn.Module):
        def __init__(self, d_model: int, kernel_size: int = 5) -> None:
            super().__init__()
            self.splitting = Splitting()
            self.modules_even = CausalConvBlock(d_model, kernel_size)
            self.modules_odd = CausalConvBlock(d_model, kernel_size)
            self.interactor_even = CausalConvBlock(d_model, kernel_size)
            self.interactor_odd = CausalConvBlock(d_model, kernel_size)

        def forward(self, values: Any) -> tuple[Any, Any]:
            even, odd = self.splitting(values)
            even = even.permute(0, 2, 1)
            odd = odd.permute(0, 2, 1)
            even_temp = even.mul(torch.exp(self.modules_even(odd)))
            odd_temp = odd.mul(torch.exp(self.modules_odd(even)))
            even_update = even_temp + self.interactor_even(odd_temp)
            odd_update = odd_temp - self.interactor_odd(even_temp)
            return even_update.permute(0, 2, 1), odd_update.permute(0, 2, 1)

    class SCINetTree(nn.Module):
        def __init__(
            self,
            d_model: int,
            current_level: int = 3,
            kernel_size: int = 5,
        ) -> None:
            super().__init__()
            self.current_level = current_level
            self.working_block = SCIBlock(d_model, kernel_size)
            if current_level != 0:
                self.odd_tree = SCINetTree(
                    d_model,
                    current_level - 1,
                    kernel_size,
                )
                self.even_tree = SCINetTree(
                    d_model,
                    current_level - 1,
                    kernel_size,
                )

        @staticmethod
        def _interleave(even: Any, odd: Any) -> Any:
            even_first = even.permute(1, 0, 2)
            odd_first = odd.permute(1, 0, 2)
            rows = []
            for index in range(min(even_first.shape[0], odd_first.shape[0])):
                rows.append(even_first[index].unsqueeze(0))
                rows.append(odd_first[index].unsqueeze(0))
            if even_first.shape[0] > odd_first.shape[0]:
                rows.append(even_first[-1].unsqueeze(0))
            return torch.cat(rows, dim=0).permute(1, 0, 2)

        def forward(self, values: Any) -> Any:
            odd_length = values.shape[1] % 2 == 1
            if odd_length:
                values = torch.cat((values, values[:, -1:, :]), dim=1)
            even, odd = self.working_block(values)
            if odd_length:
                odd = odd[:, :-1]
            if self.current_level == 0:
                return self._interleave(even, odd)
            return self._interleave(self.even_tree(even), self.odd_tree(odd))

    class SCINet(base_model):
        """Position-univariate one-stack SCINet for NeuralForecast windows."""

        EXOGENOUS_FUTR = False
        EXOGENOUS_HIST = False
        EXOGENOUS_STAT = False
        MULTIVARIATE = False
        RECURRENT = False

        def __init__(
            self,
            h: int,
            architecture_profile: str,
            training_profile: str,
            loss: Any = None,
            valid_loss: Any = None,
            learning_rate: float = 1e-3,
            batch_size: int = 32,
            valid_batch_size: int | None = None,
            windows_batch_size: int = 128,
            inference_windows_batch_size: int = 128,
            scaler_type: str = "identity",
            random_seed: int = 1,
            alias: str | None = None,
            **trainer_kwargs: Any,
        ) -> None:
            if loss is None:
                loss = losses.MAE()
            architecture = resolve_architecture(h, architecture_profile)
            training = resolve_training(training_profile)
            if getattr(loss, "outputsize_multiplier", None) != 1:
                raise ValueError("SCINet v1 supports point training losses only")
            if valid_loss is not None:
                if getattr(valid_loss, "outputsize_multiplier", None) != 1:
                    raise ValueError("SCINet v1 supports point validation losses only")

            super().__init__(
                h=h,
                input_size=architecture.input_size,
                hist_exog_list=None,
                stat_exog_list=None,
                futr_exog_list=None,
                exclude_insample_y=False,
                loss=loss,
                valid_loss=valid_loss,
                max_steps=training.max_steps,
                learning_rate=learning_rate,
                num_lr_decays=-1,
                early_stop_patience_steps=-1,
                val_check_steps=training.val_check_steps,
                batch_size=batch_size,
                valid_batch_size=valid_batch_size,
                windows_batch_size=windows_batch_size,
                inference_windows_batch_size=inference_windows_batch_size,
                start_padding_enabled=False,
                training_data_availability_threshold=0.0,
                step_size=1,
                scaler_type=scaler_type,
                random_seed=random_seed,
                drop_last_loader=False,
                alias=alias,
                **trainer_kwargs,
            )
            self.tree = SCINetTree(
                d_model=1,
                current_level=architecture.tree_level,
                kernel_size=architecture.kernel_size,
            )
            self.projection = nn.Conv1d(
                self.input_size,
                self.input_size + self.h,
                kernel_size=1,
                stride=1,
                bias=False,
            )
            self.pe_hidden_size = 2
            inv_timescales = torch.ones(1, dtype=torch.float32)
            self.register_buffer("inv_timescales", inv_timescales)

            observed = sum(parameter.numel() for parameter in self.parameters())
            if observed != architecture.expected_parameter_count:
                raise ValueError(
                    "SCINet parameter count mismatch: "
                    f"expected {architecture.expected_parameter_count}, got {observed}"
                )
            module_names = [type(module).__name__ for module in self.modules()]
            if module_names.count("SCIBlock") != architecture.sci_blocks:
                raise ValueError("SCINet SCIBlock count mismatch")
            if module_names.count("CausalConvBlock") != architecture.causal_conv_blocks:
                raise ValueError("SCINet CausalConvBlock count mismatch")

            self.loto_model_id = "nf-local-auto-scinet"
            self.loto_architecture = architecture.model_dump(mode="json")
            self.loto_training = training.model_dump(mode="json")
            self.loto_point_loss_only = True
            self.loto_position_univariate = True
            self.loto_stacks = 1

        def _position_encoding(self, values: Any) -> Any:
            length = values.shape[1]
            position = torch.arange(
                length,
                dtype=values.dtype,
                device=values.device,
            )
            scaled = position.unsqueeze(1) * self.inv_timescales.to(
                dtype=values.dtype,
            ).unsqueeze(0)
            signal = torch.cat([torch.sin(scaled), torch.cos(scaled)], dim=1)
            signal = functional.pad(
                signal,
                (0, 0, 0, self.pe_hidden_size % 2),
            )
            return signal.view(1, length, self.pe_hidden_size)[:, :, :1]

        def forward(self, windows_batch: dict[str, Any]) -> Any:
            insample_y = windows_batch["insample_y"]
            if insample_y.ndim != 3 or insample_y.shape[-1] != 1:
                raise ValueError("SCINet expects insample_y shape [batch, input_size, 1]")
            if insample_y.shape[1] != self.input_size:
                raise ValueError("SCINet input_size does not match the window")
            if not torch.isfinite(insample_y).all().item():
                raise ValueError("SCINet input must contain finite values only")

            means = insample_y.mean(1, keepdim=True).detach()
            normalized = insample_y - means
            stdev = torch.sqrt(
                torch.var(
                    normalized,
                    dim=1,
                    keepdim=True,
                    unbiased=False,
                )
                + 1e-5
            )
            normalized = normalized / stdev
            normalized = normalized + self._position_encoding(normalized)

            transformed = self.tree(normalized)
            transformed = transformed + normalized
            projected = self.projection(transformed)
            restored = projected * stdev + means
            forecast = restored[:, -self.h :, :]
            if forecast.shape != (insample_y.shape[0], self.h, 1):
                raise ValueError("SCINet produced an invalid forecast shape")
            if not torch.isfinite(forecast).all().item():
                raise ValueError("SCINet output contains non-finite values")
            return forecast

    for cls in (Splitting, CausalConvBlock, SCIBlock, SCINetTree, SCINet):
        cls.__module__ = module_name
    SCINet.__name__ = "SCINet"
    SCINet.__qualname__ = "SCINet"
    return SCINet
