from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from loto.toto2_campaign.raw_history_export import FORMAL_GAMES, sha256_file
from loto.toto2_campaign.raw_history_verify import verify_export_bundle

APPROVAL_SCOPE = "toto2_4m_runtime_request_generation"
APPROVAL_TOKEN = "APPROVE-TOTO2-HISTORY-EXPORT"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ReviewFlags(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_query_reviewed: bool
    database_snapshot_reviewed: bool
    row_counts_reviewed: bool
    cutoff_dates_reviewed: bool
    position_ranges_reviewed: bool

    def all_confirmed(self) -> bool:
        return all(self.model_dump().values())


class GameBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    game_id: str
    json_path: str
    json_sha256: str
    parquet_path: str
    parquet_sha256: str
    draw_count: int
    position_count: int
    first_ds: str
    last_ds: str
    observed_min: int
    observed_max: int

    @field_validator("json_sha256", "parquet_sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if _SHA256_RE.fullmatch(value) is None:
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value


class ExportBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    export_root: str
    verification_path: str
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
    games: dict[str, GameBinding]

    @field_validator(
        "export_manifest_sha256",
        "sha256s_sha256",
        "verification_sha256",
        "query_sha256",
        "database_snapshot_sha256",
    )
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if _SHA256_RE.fullmatch(value) is None:
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value

    @model_validator(mode="after")
    def _validate_games(self) -> ExportBinding:
        if set(self.games) != set(FORMAL_GAMES):
            raise ValueError("binding must cover the exact formal game set")
        for game_id, game in self.games.items():
            if game.game_id != game_id:
                raise ValueError(f"binding game identity mismatch: {game_id}")
        return self


class HistoryApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    status: Literal["PENDING", "APPROVED"]
    approval_scope: Literal["toto2_4m_runtime_request_generation"]
    reviewer: str
    reviewed_at: str
    review_flags: ReviewFlags
    binding: ExportBinding


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_bytes(path, _canonical_json_bytes(payload))


def _require_regular_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"required file is missing or unsafe: {path}")


def _require_outside_export_root(path: Path, export_root: Path, label: str) -> None:
    resolved = path.resolve()
    root = export_root.resolve()
    if resolved == root or resolved.is_relative_to(root):
        raise ValueError(f"{label} must be stored outside the immutable export root")


def _validate_utc_timestamp(value: str) -> str:
    if not value.endswith("Z"):
        raise ValueError("reviewed_at must end in Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("reviewed_at must be a valid ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("reviewed_at must be UTC")
    return value


def _verification_games(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = payload.get("games")
    if not isinstance(rows, list):
        raise ValueError("verification games must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("verification game entry must be an object")
        game_id = row.get("game_id")
        if not isinstance(game_id, str) or game_id in result:
            raise ValueError(f"invalid or duplicate verification game: {game_id!r}")
        result[game_id] = row
    if set(result) != set(FORMAL_GAMES):
        raise ValueError("verification does not cover the exact formal game set")
    return result


def build_export_binding(export_root: Path, verification_path: Path) -> ExportBinding:
    if not export_root.is_dir() or export_root.is_symlink():
        raise ValueError(f"export root is missing or unsafe: {export_root}")
    _require_regular_file(verification_path)
    _require_outside_export_root(verification_path, export_root, "verification output")

    fresh = verify_export_bundle(export_root)
    verification = _load_object(verification_path)
    if verification.get("status") != "VERIFIED":
        raise ValueError("verification status must be VERIFIED")
    if Path(str(verification.get("export_root", ""))).resolve() != export_root.resolve():
        raise ValueError("verification export_root does not match the selected export")
    if verification.get("future_actuals_used") is not False:
        raise ValueError("verification must record future_actuals_used=false")
    if verification.get("raw_data_modified") is not False:
        raise ValueError("verification must record raw_data_modified=false")
    if fresh != verification:
        raise ValueError("saved verification differs from a fresh independent verification")

    manifest_path = export_root / "EXPORT_MANIFEST.json"
    sha256s_path = export_root / "SHA256SUMS"
    query_path = export_root / "RAW_QUERY.sql"
    snapshot_path = export_root / "DATABASE_SNAPSHOT.json"
    for path in (manifest_path, sha256s_path, query_path, snapshot_path):
        _require_regular_file(path)

    manifest = _load_object(manifest_path)
    verification_by_game = _verification_games(verification)
    manifest_games = manifest.get("games")
    if not isinstance(manifest_games, dict) or set(manifest_games) != set(FORMAL_GAMES):
        raise ValueError("export manifest games are incomplete")

    games: dict[str, GameBinding] = {}
    for game_id in FORMAL_GAMES:
        entry = manifest_games[game_id]
        if not isinstance(entry, dict):
            raise ValueError(f"invalid export manifest game entry: {game_id}")
        json_path = export_root / f"{game_id}.json"
        parquet_path = export_root / f"{game_id}.parquet"
        _require_regular_file(json_path)
        _require_regular_file(parquet_path)
        json_sha256 = sha256_file(json_path)
        parquet_sha256 = sha256_file(parquet_path)
        verified = verification_by_game[game_id]
        expected_pairs = (
            (entry.get("json_sha256"), json_sha256, "manifest JSON"),
            (entry.get("parquet_sha256"), parquet_sha256, "manifest Parquet"),
            (verified.get("json_sha256"), json_sha256, "verification JSON"),
            (verified.get("parquet_sha256"), parquet_sha256, "verification Parquet"),
        )
        for expected, actual, label in expected_pairs:
            if expected != actual:
                raise ValueError(f"{label} hash mismatch: {game_id}")
        if verified.get("draw_count") != entry.get("draw_count"):
            raise ValueError(f"verification draw count mismatch: {game_id}")
        games[game_id] = GameBinding(
            game_id=game_id,
            json_path=json_path.name,
            json_sha256=json_sha256,
            parquet_path=parquet_path.name,
            parquet_sha256=parquet_sha256,
            draw_count=int(entry["draw_count"]),
            position_count=int(entry["position_count"]),
            first_ds=str(entry["first_ds"]),
            last_ds=str(entry["last_ds"]),
            observed_min=int(entry["observed_min"]),
            observed_max=int(entry["observed_max"]),
        )

    return ExportBinding(
        schema_version=1,
        export_root=str(export_root.resolve()),
        verification_path=str(verification_path.resolve()),
        export_manifest_sha256=sha256_file(manifest_path),
        sha256s_sha256=sha256_file(sha256s_path),
        verification_sha256=sha256_file(verification_path),
        query_sha256=sha256_file(query_path),
        database_snapshot_sha256=sha256_file(snapshot_path),
        source_schema=manifest.get("source_schema"),
        source_table=manifest.get("source_table"),
        source_ts_type=manifest.get("source_ts_type"),
        source_mode=manifest.get("source_mode"),
        future_actuals_used=manifest.get("future_actuals_used"),
        raw_data_modified=False,
        games=games,
    )


def create_pending_approval(
    export_root: Path,
    verification_path: Path,
    output_path: Path,
) -> HistoryApproval:
    if output_path.exists():
        raise FileExistsError(f"approval output already exists: {output_path}")
    _require_outside_export_root(output_path, export_root, "approval output")
    approval = HistoryApproval(
        schema_version=1,
        status="PENDING",
        approval_scope=APPROVAL_SCOPE,
        reviewer="",
        reviewed_at="",
        review_flags=ReviewFlags(
            source_query_reviewed=False,
            database_snapshot_reviewed=False,
            row_counts_reviewed=False,
            cutoff_dates_reviewed=False,
            position_ranges_reviewed=False,
        ),
        binding=build_export_binding(export_root, verification_path),
    )
    _atomic_write_json(output_path, approval.model_dump(mode="json"))
    return approval


def approve_pending(
    export_root: Path,
    verification_path: Path,
    pending_path: Path,
    output_path: Path,
    *,
    reviewer: str,
    reviewed_at: str,
    approval_token: str,
    review_flags: ReviewFlags,
) -> HistoryApproval:
    if approval_token != APPROVAL_TOKEN:
        raise ValueError("approval token mismatch")
    if not reviewer.strip():
        raise ValueError("reviewer must be non-empty")
    _validate_utc_timestamp(reviewed_at)
    if not review_flags.all_confirmed():
        raise ValueError("all history review flags must be confirmed")
    _require_regular_file(pending_path)
    if output_path.exists():
        raise FileExistsError(f"approval output already exists: {output_path}")
    _require_outside_export_root(pending_path, export_root, "pending approval")
    _require_outside_export_root(output_path, export_root, "approved record")

    pending = HistoryApproval.model_validate(_load_object(pending_path))
    if pending.status != "PENDING":
        raise ValueError("input approval record must be PENDING")
    fresh_binding = build_export_binding(export_root, verification_path)
    if pending.binding != fresh_binding:
        raise ValueError("pending approval binding no longer matches the export")

    approved = HistoryApproval(
        schema_version=1,
        status="APPROVED",
        approval_scope=APPROVAL_SCOPE,
        reviewer=reviewer.strip(),
        reviewed_at=reviewed_at,
        review_flags=review_flags,
        binding=fresh_binding,
    )
    _atomic_write_json(output_path, approved.model_dump(mode="json"))
    return approved


def validate_approved_handoff(
    export_root: Path,
    verification_path: Path,
    approval_path: Path,
) -> HistoryApproval:
    _require_regular_file(approval_path)
    _require_outside_export_root(approval_path, export_root, "approved record")
    approval = HistoryApproval.model_validate(_load_object(approval_path))
    if approval.status != "APPROVED":
        raise ValueError("history approval status must be APPROVED")
    if not approval.reviewer.strip():
        raise ValueError("history approval reviewer must be non-empty")
    _validate_utc_timestamp(approval.reviewed_at)
    if not approval.review_flags.all_confirmed():
        raise ValueError("all history review flags must be true")
    fresh_binding = build_export_binding(export_root, verification_path)
    if approval.binding != fresh_binding:
        raise ValueError("approved history binding differs from the current export")
    return approval


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def materialize_approved_histories(
    export_root: Path,
    verification_path: Path,
    approval_path: Path,
    destination: Path,
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"approved-history destination already exists: {destination}")
    approval = validate_approved_handoff(export_root, verification_path, approval_path)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise FileExistsError(f"temporary approved-history path already exists: {temporary}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()

    try:
        copied: dict[str, str] = {}
        for game_id in FORMAL_GAMES:
            expected = approval.binding.games[game_id].json_sha256
            source = export_root / f"{game_id}.json"
            payload = source.read_bytes()
            if _sha256_bytes(payload) != expected:
                raise ValueError(f"history JSON changed during materialization: {game_id}")
            target = temporary / source.name
            _atomic_write_bytes(target, payload)
            if sha256_file(target) != expected:
                raise RuntimeError(f"materialized history hash mismatch: {game_id}")
            copied[target.name] = expected

        evidence_sources = {
            "history_verification.json": verification_path,
            "history_approval.json": approval_path,
        }
        for filename, source in evidence_sources.items():
            payload = source.read_bytes()
            target = temporary / filename
            _atomic_write_bytes(target, payload)
            copied[filename] = _sha256_bytes(payload)

        fresh_binding = build_export_binding(export_root, verification_path)
        if fresh_binding != approval.binding:
            raise ValueError("export changed while approved histories were being materialized")

        handoff = {
            "schema_version": 1,
            "status": "MATERIALIZED_APPROVED_HISTORY",
            "materialized_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "approval_scope": APPROVAL_SCOPE,
            "approval_sha256": sha256_file(approval_path),
            "verification_sha256": sha256_file(verification_path),
            "export_manifest_sha256": approval.binding.export_manifest_sha256,
            "source_export_root": approval.binding.export_root,
            "reviewer": approval.reviewer,
            "reviewed_at": approval.reviewed_at,
            "future_actuals_used": False,
            "raw_data_modified": False,
            "copied_files": copied,
        }
        _atomic_write_json(temporary / "HISTORY_HANDOFF.json", handoff)
        temporary.replace(destination)
        return handoff
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
