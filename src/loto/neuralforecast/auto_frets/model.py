"""NeuralForecast FreTS class factory."""

from __future__ import annotations

from typing import Any

from .contracts import (
    FRETS_CHANNEL_INDEPENDENCE,
    FRETS_PRECISION,
    resolve_architecture,
    resolve_training,
)


def build_frets_class(
    *,
    base_model: type[Any],
    functional: Any,
    losses: Any,
    nn: Any,
    torch: Any,
    module_name: str,
) -> type[Any]:
    class FreTS(base_model):
        """Position-univariate FreTS adapted to NeuralForecast windows."""

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
            precision: str = FRETS_PRECISION,
            alias: str | None = None,
            **trainer_kwargs: Any,
        ) -> None:
            if loss is None:
                loss = losses.MAE()
            architecture = resolve_architecture(h, architecture_profile)
            training = resolve_training(training_profile)
            if getattr(loss, "outputsize_multiplier", None) != 1:
                raise ValueError("FreTS v1 supports point training losses only")
            if valid_loss is not None:
                if getattr(valid_loss, "outputsize_multiplier", None) != 1:
                    raise ValueError("FreTS v1 supports point validation losses only")
            if precision != FRETS_PRECISION:
                raise ValueError("FreTS v1 supports precision=32-true only")

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
                precision=precision,
                alias=alias,
                **trainer_kwargs,
            )

            self.embed_size = architecture.embed_size
            self.hidden_size = architecture.hidden_size
            self.sparsity_threshold = architecture.sparsity_threshold
            self.scale = architecture.scale
            self.channel_independence = FRETS_CHANNEL_INDEPENDENCE
            self.embeddings = nn.Parameter(torch.randn(1, self.embed_size))
            self.r1 = nn.Parameter(
                self.scale * torch.randn(self.embed_size, self.embed_size)
            )
            self.i1 = nn.Parameter(
                self.scale * torch.randn(self.embed_size, self.embed_size)
            )
            self.rb1 = nn.Parameter(self.scale * torch.randn(self.embed_size))
            self.ib1 = nn.Parameter(self.scale * torch.randn(self.embed_size))
            self.r2 = nn.Parameter(
                self.scale * torch.randn(self.embed_size, self.embed_size)
            )
            self.i2 = nn.Parameter(
                self.scale * torch.randn(self.embed_size, self.embed_size)
            )
            self.rb2 = nn.Parameter(self.scale * torch.randn(self.embed_size))
            self.ib2 = nn.Parameter(
                self.scale * torch.randn(self.embed_size)
            )
            self.fc = nn.Sequential(
                nn.Linear(self.input_size * self.embed_size, self.hidden_size),
                nn.LeakyReLU(),
                nn.Linear(self.hidden_size, self.h),
            )
            observed = sum(parameter.numel() for parameter in self.parameters())
            if observed != architecture.expected_parameter_count:
                raise ValueError(
                    "FreTS parameter count mismatch: "
                    f"expected {architecture.expected_parameter_count}, got {observed}"
                )
            self.loto_model_id = "nf-local-auto-frets"
            self.loto_architecture = architecture.model_dump(mode="json")
            self.loto_training = training.model_dump(mode="json")
            self.loto_point_loss_only = True
            self.loto_fft_dtype = "float32"
            self.loto_channel_frequency_mixing = False

        def _temporal_frequency_mlp(self, values: Any) -> Any:
            spectrum = torch.fft.rfft(values, dim=2, norm="ortho")
            real = functional.relu(
                torch.einsum("bnti,io->bnto", spectrum.real, self.r1)
                - torch.einsum("bnti,io->bnto", spectrum.imag, self.i1)
                + self.rb1
            )
            imaginary = functional.relu(
                torch.einsum("bnti,io->bnto", spectrum.imag, self.r1)
                + torch.einsum("bnti,io->bnto", spectrum.real, self.i1)
                + self.ib1
            )
            stacked = torch.stack((real, imaginary), dim=-1)
            sparse = functional.softshrink(
                stacked,
                lambd=self.sparsity_threshold,
            )
            complex_values = torch.view_as_complex(sparse.contiguous())
            return torch.fft.irfft(
                complex_values,
                n=self.input_size,
                dim=2,
                norm="ortho",
            )

        def forward(self, windows_batch: dict[str, Any]) -> Any:
            insample_y = windows_batch["insample_y"]
            if insample_y.ndim != 3 or insample_y.shape[-1] != 1:
                raise ValueError(
                    "FreTS expects insample_y shape [batch, input_size, 1]"
                )
            if insample_y.shape[1] != self.input_size:
                raise ValueError("FreTS input_size does not match the training window")
            if insample_y.dtype != torch.float32:
                raise ValueError("FreTS v1 requires float32 input for FFT operations")
            if not torch.isfinite(insample_y).all().item():
                raise ValueError("FreTS input must contain finite values only")

            embedded = insample_y.permute(0, 2, 1).unsqueeze(-1)
            embedded = embedded * self.embeddings
            residual = embedded
            transformed = self._temporal_frequency_mlp(embedded)
            transformed = transformed + residual
            batch_size = transformed.shape[0]
            projected = self.fc(transformed.reshape(batch_size, 1, -1))
            forecast = projected.permute(0, 2, 1)
            if not torch.isfinite(forecast).all().item():
                raise ValueError("FreTS output contains non-finite values")
            return forecast

    FreTS.__name__ = "FreTS"
    FreTS.__qualname__ = "FreTS"
    FreTS.__module__ = module_name
    return FreTS
