"""NeuralForecast SegRNN class factory."""

from __future__ import annotations

from typing import Any

from .contracts import resolve_architecture, resolve_training


def build_segrnn_class(
    *,
    base_model: type[Any],
    losses: Any,
    nn: Any,
    torch: Any,
    module_name: str,
) -> type[Any]:
    class SegRNN(base_model):
        """Position-univariate SegRNN adapted to NeuralForecast windows."""

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
            windows_batch_size: int = 256,
            inference_windows_batch_size: int = 256,
            dropout: float = 0.1,
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
                raise ValueError("SegRNN v1 supports point training losses only")
            if valid_loss is not None:
                if getattr(valid_loss, "outputsize_multiplier", None) != 1:
                    raise ValueError("SegRNN v1 supports point validation losses only")
            if not 0.0 <= dropout < 0.5:
                raise ValueError("dropout must be in [0, 0.5)")

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

            self.seg_len = architecture.seg_len
            self.seg_num_x = architecture.input_size // architecture.seg_len
            self.seg_num_y = h // architecture.seg_len
            self.d_model = architecture.d_model
            self.value_embedding = nn.Sequential(
                nn.Linear(self.seg_len, self.d_model),
                nn.ReLU(),
            )
            self.rnn = nn.GRU(
                input_size=self.d_model,
                hidden_size=self.d_model,
                num_layers=1,
                bias=True,
                batch_first=True,
                bidirectional=False,
            )
            self.position_embedding = nn.Parameter(
                torch.randn(self.seg_num_y, self.d_model // 2)
            )
            self.channel_embedding = nn.Parameter(torch.randn(1, self.d_model // 2))
            self.output_projection = nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(self.d_model, self.seg_len),
            )
            self.loto_model_id = "nf-local-auto-segrnn"
            self.loto_architecture = architecture.model_dump(mode="json")
            self.loto_training = training.model_dump(mode="json")
            self.loto_point_loss_only = True

        def forward(self, windows_batch: dict[str, Any]) -> Any:
            insample_y = windows_batch["insample_y"]
            if insample_y.ndim != 3 or insample_y.shape[-1] != 1:
                raise ValueError(
                    "SegRNN expects insample_y shape [batch, input_size, 1]"
                )
            if insample_y.shape[1] != self.input_size:
                raise ValueError(
                    "SegRNN input_size does not match the training window"
                )

            x = insample_y.squeeze(-1)
            batch_size = x.shape[0]
            sequence_last = x[:, -1:].detach()
            normalized = x - sequence_last
            segments = normalized.reshape(
                batch_size,
                self.seg_num_x,
                self.seg_len,
            )
            embedded = self.value_embedding(segments)
            _, hidden = self.rnn(embedded)

            channel = self.channel_embedding.expand(self.seg_num_y, -1)
            decoder_seed = torch.cat(
                [self.position_embedding, channel],
                dim=-1,
            )
            decoder_seed = decoder_seed.unsqueeze(0).expand(batch_size, -1, -1)
            decoder_seed = decoder_seed.reshape(
                batch_size * self.seg_num_y,
                1,
                self.d_model,
            )
            decoder_hidden = hidden.unsqueeze(2).expand(
                -1,
                -1,
                self.seg_num_y,
                -1,
            )
            decoder_hidden = decoder_hidden.reshape(
                1,
                batch_size * self.seg_num_y,
                self.d_model,
            )
            _, decoded = self.rnn(decoder_seed, decoder_hidden)
            forecast = self.output_projection(decoded.squeeze(0))
            forecast = forecast.reshape(batch_size, self.h) + sequence_last
            return forecast.unsqueeze(-1)

    SegRNN.__name__ = "SegRNN"
    SegRNN.__qualname__ = "SegRNN"
    SegRNN.__module__ = module_name
    return SegRNN
