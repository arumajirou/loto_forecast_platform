from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

UPSTREAM_REPOSITORY = "https://github.com/thuml/Time-Series-Library"
UPSTREAM_REVISION = "4e938a1767106324dd753b2a44832bf870a0252e"
PROTOCOL_VERSION = "1.0"


class SourcePolicy(StrEnum):
    PINNED = "pinned"
    TEST_FIXTURE = "test_fixture"


class ProviderStatus(StrEnum):
    PASS = "PASS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class Operation(StrEnum):
    DISCOVER = "discover"
    DLINEAR_FIT_SAVE = "dlinear_fit_save"
    DLINEAR_LOAD_PREDICT = "dlinear_load_predict"
    TSMIXER_FIT_SAVE = "tsmixer_fit_save"
    TSMIXER_LOAD_PREDICT = "tsmixer_load_predict"
    LIGHTTS_FIT_SAVE = "lightts_fit_save"
    LIGHTTS_LOAD_PREDICT = "lightts_load_predict"
    SEGRNN_FIT_SAVE = "segrnn_fit_save"
    SEGRNN_LOAD_PREDICT = "segrnn_load_predict"
    FRETS_FIT_SAVE = "frets_fit_save"
    FRETS_LOAD_PREDICT = "frets_load_predict"
    SCINET_FIT_SAVE = "scinet_fit_save"
    SCINET_LOAD_PREDICT = "scinet_load_predict"
    TIMEFILTER_FIT_SAVE = "timefilter_fit_save"
    TIMEFILTER_LOAD_PREDICT = "timefilter_load_predict"
    TIDE_FIT_SAVE = "tide_fit_save"
    TIDE_LOAD_PREDICT = "tide_load_predict"
    FILM_FIT_SAVE = "film_fit_save"
    FILM_LOAD_PREDICT = "film_load_predict"
    VERIFY_ROUNDTRIP = "verify_roundtrip"


class GameGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: str = Field(min_length=1)
    position_columns: tuple[str, ...] = Field(min_length=1)
    draw_number_column: str = "draw_no"
    draw_date_column: str = "draw_date"
    candidate_min: int
    candidate_max: int
    draw_order_semantics: Literal["draw_sequence"] = "draw_sequence"

    @model_validator(mode="after")
    def validate_geometry(self) -> GameGeometry:
        if len(set(self.position_columns)) != len(self.position_columns):
            raise ValueError("position_columns must be unique")
        if self.candidate_min > self.candidate_max:
            raise ValueError("candidate_min must be <= candidate_max")
        return self


class SplitContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train_end_exclusive: int = Field(gt=0)
    validation_end_exclusive: int = Field(gt=0)
    holdout_end_exclusive: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_boundaries(self) -> SplitContract:
        if not (
            self.train_end_exclusive
            < self.validation_end_exclusive
            <= self.holdout_end_exclusive
        ):
            raise ValueError("required order: train_end < validation_end <= holdout_end")
        return self


class ProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    operation: Operation
    source_root: Path
    output_dir: Path
    model_name: str = "DLinear"
    source_policy: SourcePolicy = SourcePolicy.PINNED
    device: Literal["cpu"] = "cpu"
    seed: int = 1
    seq_len: int = Field(default=16, ge=4)
    pred_len: int = Field(default=1, ge=1)
    channels: int = Field(default=1, ge=1)
    train_steps: int = Field(default=1, ge=0, le=100)
    d_model: int = Field(default=16, ge=4)
    dropout: float = Field(default=0.0, ge=0.0, lt=1.0)
    e_layers: int = Field(default=2, ge=1, le=32)
    lightts_chunk_size: int = Field(default=24, ge=1, le=4096)
    lightts_allow_padding: bool = False
    segrnn_seg_len: int = Field(default=2, ge=1, le=4096)
    frets_channel_independence: Literal["0", "1"] = "1"
    scinet_stacks: Literal[1, 2] = 1
    timefilter_patch_len: int = Field(default=4, ge=1, le=4096)
    timefilter_n_heads: int = Field(default=2, ge=1, le=128)
    timefilter_d_ff: int = Field(default=32, ge=1, le=65536)
    timefilter_alpha: float = Field(default=0.1, ge=0.0, le=1.0)
    timefilter_top_p: float = Field(default=0.5, ge=0.0, le=1.0)
    timefilter_pos: bool = True
    tide_d_layers: int = Field(default=1, ge=1, le=32)
    tide_d_ff: int = Field(default=32, ge=1, le=65536)
    tide_freq: Literal["h", "t", "s", "m", "a", "w", "d", "b"] = "h"
    checkpoint_path: Path | None = None
    input_path: Path | None = None
    before_prediction_path: Path | None = None
    after_prediction_path: Path | None = None
    rtol: float = Field(default=1e-8, ge=0)
    atol: float = Field(default=1e-8, ge=0)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> ProviderRequest:
        dlinear_ops = {
            Operation.DLINEAR_FIT_SAVE,
            Operation.DLINEAR_LOAD_PREDICT,
        }
        tsmixer_ops = {
            Operation.TSMIXER_FIT_SAVE,
            Operation.TSMIXER_LOAD_PREDICT,
        }
        lightts_ops = {
            Operation.LIGHTTS_FIT_SAVE,
            Operation.LIGHTTS_LOAD_PREDICT,
        }
        segrnn_ops = {
            Operation.SEGRNN_FIT_SAVE,
            Operation.SEGRNN_LOAD_PREDICT,
        }
        frets_ops = {
            Operation.FRETS_FIT_SAVE,
            Operation.FRETS_LOAD_PREDICT,
        }
        scinet_ops = {
            Operation.SCINET_FIT_SAVE,
            Operation.SCINET_LOAD_PREDICT,
        }
        timefilter_ops = {
            Operation.TIMEFILTER_FIT_SAVE,
            Operation.TIMEFILTER_LOAD_PREDICT,
        }
        tide_ops = {
            Operation.TIDE_FIT_SAVE,
            Operation.TIDE_LOAD_PREDICT,
        }
        film_ops = {
            Operation.FILM_FIT_SAVE,
            Operation.FILM_LOAD_PREDICT,
        }
        load_ops = {
            Operation.DLINEAR_LOAD_PREDICT,
            Operation.TSMIXER_LOAD_PREDICT,
            Operation.LIGHTTS_LOAD_PREDICT,
            Operation.SEGRNN_LOAD_PREDICT,
            Operation.FRETS_LOAD_PREDICT,
            Operation.SCINET_LOAD_PREDICT,
            Operation.TIMEFILTER_LOAD_PREDICT,
            Operation.TIDE_LOAD_PREDICT,
            Operation.FILM_LOAD_PREDICT,
        }
        if self.operation in dlinear_ops and self.model_name != "DLinear":
            raise ValueError("DLinear operations require model_name=DLinear")
        if self.operation in tsmixer_ops and self.model_name != "TSMixer":
            raise ValueError("TSMixer operations require model_name=TSMixer")
        if self.operation in lightts_ops and self.model_name != "LightTS":
            raise ValueError("LightTS operations require model_name=LightTS")
        if self.operation in segrnn_ops and self.model_name != "SegRNN":
            raise ValueError("SegRNN operations require model_name=SegRNN")
        if self.operation in frets_ops and self.model_name != "FreTS":
            raise ValueError("FreTS operations require model_name=FreTS")
        if self.operation in scinet_ops and self.model_name != "SCINet":
            raise ValueError("SCINet operations require model_name=SCINet")
        if self.operation in timefilter_ops and self.model_name != "TimeFilter":
            raise ValueError("TimeFilter operations require model_name=TimeFilter")
        if self.operation in tide_ops and self.model_name != "TiDE":
            raise ValueError("TiDE operations require model_name=TiDE")
        if self.operation in film_ops and self.model_name != "FiLM":
            raise ValueError("FiLM operations require model_name=FiLM")
        if self.operation in lightts_ops:
            if self.d_model < 16:
                raise ValueError("LightTS requires d_model >= 16")
            if self.d_model % 4 != 0:
                raise ValueError("LightTS requires d_model divisible by 4")
            chunk_size = min(self.pred_len, self.seq_len, self.lightts_chunk_size)
            padding_length = (-self.seq_len) % chunk_size
            if padding_length and not self.lightts_allow_padding:
                raise ValueError(
                    "LightTS padding requires lightts_allow_padding=true: "
                    f"padding_length={padding_length}"
                )
        if self.operation == Operation.SEGRNN_FIT_SAVE:
            if self.d_model % 2 != 0:
                raise ValueError("SegRNN requires even d_model")
            if self.seq_len % self.segrnn_seg_len != 0:
                raise ValueError("SegRNN requires seq_len divisible by segrnn_seg_len")
            if self.pred_len % self.segrnn_seg_len != 0:
                raise ValueError("SegRNN requires pred_len divisible by segrnn_seg_len")
        if self.operation == Operation.SCINET_FIT_SAVE:
            if self.seq_len < 8:
                raise ValueError("SCINet requires seq_len >= 8 for tree level 3")
            if self.dropout != 0.0:
                raise ValueError("SCINet requires dropout=0.0 because upstream ignores it")
        if self.operation == Operation.TIMEFILTER_FIT_SAVE:
            if self.timefilter_patch_len > self.seq_len:
                raise ValueError("TimeFilter requires patch_len <= seq_len")
            if self.seq_len % self.timefilter_patch_len != 0:
                raise ValueError("TimeFilter requires seq_len divisible by patch_len")
            if self.d_model % 2 != 0:
                raise ValueError("TimeFilter requires even d_model for positional embedding")
            if self.d_model % self.timefilter_n_heads != 0:
                raise ValueError("TimeFilter requires d_model divisible by n_heads")
            token_count = self.channels * (self.seq_len // self.timefilter_patch_len)
            if token_count > 10000:
                raise ValueError("TimeFilter token count exceeds positional limit 10000")
        if self.operation == Operation.TIDE_FIT_SAVE:
            if self.e_layers != 1 or self.tide_d_layers != 1:
                raise ValueError("TiDE certified lane requires e_layers=1 and tide_d_layers=1")
            if self.dropout != 0.0:
                raise ValueError("TiDE certified lane requires dropout=0.0")
        if self.operation == Operation.FILM_FIT_SAVE:
            if self.pred_len < 2:
                raise ValueError("FiLM certified lane requires pred_len >= 2")
            if self.seq_len < 4 * self.pred_len:
                raise ValueError("FiLM certified lane requires seq_len >= 4 * pred_len")
            if self.e_layers != 1:
                raise ValueError("FiLM certified lane requires e_layers=1")
            if self.dropout != 0.0:
                raise ValueError("FiLM certified lane requires dropout=0.0")
        if self.operation in load_ops and (
            self.checkpoint_path is None or self.input_path is None
        ):
            raise ValueError("load/predict requires checkpoint_path and input_path")
        if self.operation == Operation.VERIFY_ROUNDTRIP and (
            self.before_prediction_path is None or self.after_prediction_path is None
        ):
            raise ValueError("roundtrip verification requires both prediction paths")
        return self


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal["1.0"] = PROTOCOL_VERSION
    status: ProviderStatus
    operation: Operation
    upstream_repository: str = UPSTREAM_REPOSITORY
    upstream_revision: str = UPSTREAM_REVISION
    model_name: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
