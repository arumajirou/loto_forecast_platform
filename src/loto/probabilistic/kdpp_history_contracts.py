from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from loto.game.geometry import geometry_for
from loto.probabilistic.kdpp_certification_gate import (
    MODEL_ID,
    SCHEMA_VERSION,
    validate_sha256,
)

RAW_APPROVAL_SCOPE = "toto2_4m_runtime_request_generation"
RAW_HANDOFF_STATUS = "MATERIALIZED_APPROVED_HISTORY"
RAW_SOURCE_FILES = {
    "numbers3.json",
    "numbers4.json",
    "miniloto.json",
    "loto6.json",
    "loto7.json",
    "history_verification.json",
    "history_approval.json",
    "HISTORY_HANDOFF.json",
}
_GAME_IDS = ("numbers3", "numbers4", "miniloto", "loto6", "loto7")
_CANONICAL_GAME_IDS = {"miniloto": "mini"}


def _game_spec(game_id: str) -> tuple[int, int, int, bool]:
    geometry = geometry_for(_CANONICAL_GAME_IDS.get(game_id, game_id))
    return (
        geometry.positions,
        geometry.value_min,
        geometry.value_max,
        geometry.ascending,
    )


_GAME_SPECS: dict[str, tuple[int, int, int, bool]] = {
    game_id: _game_spec(game_id) for game_id in _GAME_IDS
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class RawReviewFlags(StrictModel):
    source_query_reviewed: Literal[True]
    database_snapshot_reviewed: Literal[True]
    row_counts_reviewed: Literal[True]
    cutoff_dates_reviewed: Literal[True]
    position_ranges_reviewed: Literal[True]


class RawGameBinding(StrictModel):
    game_id: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    json_path: str
    json_sha256: str
    parquet_path: str
    parquet_sha256: str
    draw_count: int = Field(ge=2)
    position_count: int = Field(ge=1, le=7)
    first_ds: str = Field(min_length=1)
    last_ds: str = Field(min_length=1)
    observed_min: int
    observed_max: int

    @field_validator("json_sha256", "parquet_sha256")
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)


class RawExportBinding(StrictModel):
    schema_version: Literal[1]
    export_root: str = Field(min_length=1)
    verification_path: str = Field(min_length=1)
    export_manifest_sha256: str
    sha256s_sha256: str
    verification_sha256: str
    query_sha256: str
    database_snapshot_sha256: str
    source_schema: Literal["dataset"]
    source_table: Literal["loto_y_ts_unified"]
    source_ts_type: Literal["raw"]
    source_mode: Literal["repeatable_read_read_only"]
    future_actuals_used: Literal[False]
    raw_data_modified: Literal[False]
    games: dict[str, RawGameBinding]

    @field_validator(
        "export_manifest_sha256",
        "sha256s_sha256",
        "verification_sha256",
        "query_sha256",
        "database_snapshot_sha256",
    )
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)

    @model_validator(mode="after")
    def game_set(self) -> RawExportBinding:
        if set(self.games) != set(_GAME_SPECS):
            raise ValueError("raw export binding must cover all five games")
        for name, game in self.games.items():
            if game.game_id != name:
                raise ValueError("raw export game identity mismatch")
        return self


class RawHistoryApproval(StrictModel):
    schema_version: Literal[1]
    status: Literal["APPROVED"]
    approval_scope: Literal[RAW_APPROVAL_SCOPE]
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: str = Field(min_length=1)
    review_flags: RawReviewFlags
    binding: RawExportBinding


class RawVerificationGame(StrictModel):
    game_id: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    draw_count: int = Field(ge=2)
    json_sha256: str
    parquet_sha256: str

    @field_validator("json_sha256", "parquet_sha256")
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)


class RawHistoryVerification(StrictModel):
    schema_version: Literal[1]
    status: Literal["VERIFIED"]
    export_root: str = Field(min_length=1)
    file_count: int = Field(ge=1)
    games: tuple[RawVerificationGame, ...]
    future_actuals_used: Literal[False]
    raw_data_modified: Literal[False]

    @field_validator("games", mode="before")
    @classmethod
    def tuple_games(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def game_set(self) -> RawHistoryVerification:
        names = [game.game_id for game in self.games]
        if len(names) != len(set(names)) or set(names) != set(_GAME_SPECS):
            raise ValueError("raw verification must cover each game exactly once")
        return self


class RawHistoryHandoff(StrictModel):
    schema_version: Literal[1]
    status: Literal[RAW_HANDOFF_STATUS]
    materialized_at: str = Field(min_length=1)
    approval_scope: Literal[RAW_APPROVAL_SCOPE]
    approval_sha256: str
    verification_sha256: str
    export_manifest_sha256: str
    source_export_root: str = Field(min_length=1)
    reviewer: str = Field(min_length=1, max_length=256)
    reviewed_at: str = Field(min_length=1)
    future_actuals_used: Literal[False]
    raw_data_modified: Literal[False]
    copied_files: dict[str, str]

    @field_validator("approval_sha256", "verification_sha256", "export_manifest_sha256")
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)

    @model_validator(mode="after")
    def copied_set(self) -> RawHistoryHandoff:
        expected = RAW_SOURCE_FILES - {"HISTORY_HANDOFF.json"}
        if set(self.copied_files) != expected:
            raise ValueError("raw handoff copied_files set mismatch")
        for digest in self.copied_files.values():
            validate_sha256(digest)
        return self


class PendingKDPPHistoryApproval(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    decision: Literal["PENDING"]
    bundle_root: str = Field(min_length=1)
    history_manifest_sha256: str
    history_sha256sums_sha256: str
    training_npz_sha256: str
    item_ids_json_sha256: str
    reviewer: Literal[""]
    reviewed_at_utc: None
    source_read_only_confirmed: Literal[False]
    train_only_confirmed: Literal[False]
    draw_order_confirmed: Literal[False]
    row_count_confirmed: Literal[False]
    game_geometry_confirmed: Literal[False]
    cutoff_confirmed: Literal[False]
    no_future_actuals_confirmed: Literal[False]
    no_holdout_confirmed: Literal[False]
    no_prospective_confirmed: Literal[False]

    @field_validator(
        "history_manifest_sha256",
        "history_sha256sums_sha256",
        "training_npz_sha256",
        "item_ids_json_sha256",
    )
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)


class MaterializationResult(StrictModel):
    schema_version: Literal[SCHEMA_VERSION]
    model_id: Literal[MODEL_ID]
    status: Literal["KDPP_HISTORY_BUNDLE_MATERIALIZED"]
    formal_runtime_certification: Literal[False]
    game: Literal["numbers3", "numbers4", "miniloto", "loto6", "loto7"]
    position: int | None
    row_count: int = Field(ge=2)
    cardinality: int = Field(ge=1)
    item_count: int = Field(ge=2)
    source_handoff_tree_sha256: str
    history_manifest_sha256: str
    history_sha256sums_sha256: str
    training_npz_sha256: str
    item_ids_json_sha256: str
    output_root: str = Field(min_length=1)

    @field_validator(
        "source_handoff_tree_sha256",
        "history_manifest_sha256",
        "history_sha256sums_sha256",
        "training_npz_sha256",
        "item_ids_json_sha256",
    )
    @classmethod
    def hashes(cls, value: str) -> str:
        return validate_sha256(value)
