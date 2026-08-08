from __future__ import annotations

import io
import json
import os
import shutil
import zipfile
from pathlib import Path

import numpy as np

from loto.probabilistic.kdpp_certification_gate import (
    APPROVAL_TOKEN,
    MODEL_ID,
    SCHEMA_VERSION,
    KDPPHistoryApproval,
    KDPPHistoryManifest,
    sha256_file,
    tree_sha256,
    validate_history_bundle,
    write_json,
)
from loto.probabilistic.kdpp_history_contracts import (
    _GAME_SPECS,
    RAW_APPROVAL_SCOPE,
    MaterializationResult,
    PendingKDPPHistoryApproval,
)
from loto.probabilistic.kdpp_history_source import (
    _load_object,
    _parse_utc_text,
    build_indicator_matrix,
    parse_game_history,
    validate_materialized_raw_history,
)

__all__ = [
    "RAW_APPROVAL_SCOPE",
    "approve_history_bundle",
    "build_indicator_matrix",
    "create_pending_approval",
    "materialize_kdpp_history",
    "parse_game_history",
    "tree_sha256",
    "validate_materialized_raw_history",
]


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.lib.format.write_array(buffer, array, allow_pickle=False)
    return buffer.getvalue()


def write_deterministic_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with path.open("wb") as handle:
        with zipfile.ZipFile(handle, mode="w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(arrays):
                info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o600 << 16
                archive.writestr(info, _npy_bytes(np.ascontiguousarray(arrays[name])))
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _outside_bundle(path: Path, bundle: Path, label: str) -> None:
    resolved = path.resolve()
    root = bundle.resolve()
    if resolved == root or resolved.is_relative_to(root):
        raise ValueError(f"{label} must be outside the immutable history bundle")


def materialize_kdpp_history(
    source_root: Path,
    output_root: Path,
    *,
    game: str,
    position: int | None = None,
) -> MaterializationResult:
    if output_root.exists():
        raise FileExistsError(output_root)
    handoff, approval, _ = validate_materialized_raw_history(source_root)
    if game not in _GAME_SPECS:
        raise ValueError("unsupported game")
    binding = approval.binding.games[game]
    values, _, draw_nos = parse_game_history(source_root / f"{game}.json", game=game)
    if values.shape[0] != binding.draw_count:
        raise ValueError("selected game row count differs from approved binding")
    indicators, item_ids, cardinality, target_layout = build_indicator_matrix(
        values,
        game=game,
        position=position,
    )
    temporary = output_root.with_name(f".{output_root.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise FileExistsError(temporary)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.mkdir()
    try:
        item_path = temporary / "item_ids.json"
        _atomic_write_text(
            item_path,
            json.dumps(item_ids, ensure_ascii=False, indent=2) + "\n",
        )
        training_path = temporary / "training.npz"
        write_deterministic_npz(
            training_path,
            {
                "draw_nos": draw_nos,
                "training_indicators": indicators,
            },
        )
        source_tree_hash = tree_sha256(source_root)
        manifest = KDPPHistoryManifest(
            schema_version=SCHEMA_VERSION,
            model_id=MODEL_ID,
            bundle_status="VERIFIED_REAL_HISTORY",
            data_role="TRAIN_ONLY",
            game=game,
            target_layout=target_layout,
            position=position,
            source_system=(
                "dataset.loto_y_ts_unified/repeatable_read_read_only "
                "via MATERIALIZED_APPROVED_HISTORY"
            ),
            source_snapshot=approval.binding.database_snapshot_sha256,
            source_query_sha256=approval.binding.query_sha256,
            source_data_sha256=source_tree_hash,
            created_at_utc=_parse_utc_text(handoff.materialized_at, "materialized_at"),
            train_start=1,
            train_end=len(draw_nos),
            forecast_origin=len(draw_nos) + 1,
            row_count=len(draw_nos),
            context_length=len(draw_nos),
            prediction_lengths=(1, 2, 5),
            cardinality=cardinality,
            item_count=len(item_ids),
            training_npz_sha256=sha256_file(training_path),
            item_ids_json_sha256=sha256_file(item_path),
            read_only_source=True,
            raw_data_immutable=True,
            draw_order_verified=True,
            future_actuals_included=False,
            holdout_included=False,
            prospective_included=False,
            formal_approval_required=True,
        )
        manifest_path = temporary / "history_manifest.json"
        write_json(manifest_path, manifest)
        checksums = temporary / "SHA256SUMS"
        _atomic_write_text(
            checksums,
            "".join(
                f"{sha256_file(temporary / name)}  {name}\n"
                for name in sorted(("history_manifest.json", "item_ids.json", "training.npz"))
            ),
        )
        output_root.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(output_root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return MaterializationResult(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        status="KDPP_HISTORY_BUNDLE_MATERIALIZED",
        formal_runtime_certification=False,
        game=game,
        position=position,
        row_count=len(draw_nos),
        cardinality=cardinality,
        item_count=len(item_ids),
        source_handoff_tree_sha256=tree_sha256(source_root),
        history_manifest_sha256=sha256_file(output_root / "history_manifest.json"),
        history_sha256sums_sha256=sha256_file(output_root / "SHA256SUMS"),
        training_npz_sha256=sha256_file(output_root / "training.npz"),
        item_ids_json_sha256=sha256_file(output_root / "item_ids.json"),
        output_root=str(output_root.resolve()),
    )


def create_pending_approval(bundle_root: Path, output_path: Path) -> PendingKDPPHistoryApproval:
    if output_path.exists():
        raise FileExistsError(output_path)
    _outside_bundle(output_path, bundle_root, "pending approval")
    manifest = KDPPHistoryManifest.model_validate(
        _load_object(bundle_root / "history_manifest.json")
    )
    pending = PendingKDPPHistoryApproval(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        decision="PENDING",
        bundle_root=str(bundle_root.resolve()),
        history_manifest_sha256=sha256_file(bundle_root / "history_manifest.json"),
        history_sha256sums_sha256=sha256_file(bundle_root / "SHA256SUMS"),
        training_npz_sha256=manifest.training_npz_sha256,
        item_ids_json_sha256=manifest.item_ids_json_sha256,
        reviewer="",
        reviewed_at_utc=None,
        source_read_only_confirmed=False,
        train_only_confirmed=False,
        draw_order_confirmed=False,
        row_count_confirmed=False,
        game_geometry_confirmed=False,
        cutoff_confirmed=False,
        no_future_actuals_confirmed=False,
        no_holdout_confirmed=False,
        no_prospective_confirmed=False,
    )
    write_json(output_path, pending)
    return pending


def approve_history_bundle(
    bundle_root: Path,
    pending_path: Path,
    output_path: Path,
    *,
    reviewer: str,
    reviewed_at_utc: str,
    approval_token: str,
    confirmations: dict[str, bool],
) -> KDPPHistoryApproval:
    if output_path.exists():
        raise FileExistsError(output_path)
    _outside_bundle(pending_path, bundle_root, "pending approval")
    _outside_bundle(output_path, bundle_root, "approved record")
    if approval_token != APPROVAL_TOKEN:
        raise ValueError("approval token mismatch")
    if not reviewer.strip():
        raise ValueError("reviewer must be non-empty")
    reviewed = _parse_utc_text(reviewed_at_utc, "reviewed_at_utc")
    expected_keys = {
        "source_read_only_confirmed",
        "train_only_confirmed",
        "draw_order_confirmed",
        "row_count_confirmed",
        "game_geometry_confirmed",
        "cutoff_confirmed",
        "no_future_actuals_confirmed",
        "no_holdout_confirmed",
        "no_prospective_confirmed",
    }
    if set(confirmations) != expected_keys or not all(confirmations.values()):
        raise ValueError("all approval confirmations must be true")
    pending = PendingKDPPHistoryApproval.model_validate(_load_object(pending_path))
    if Path(pending.bundle_root).resolve() != bundle_root.resolve():
        raise ValueError("pending approval bundle identity mismatch")
    checks = {
        "history_manifest_sha256": sha256_file(bundle_root / "history_manifest.json"),
        "history_sha256sums_sha256": sha256_file(bundle_root / "SHA256SUMS"),
        "training_npz_sha256": sha256_file(bundle_root / "training.npz"),
        "item_ids_json_sha256": sha256_file(bundle_root / "item_ids.json"),
    }
    if any(getattr(pending, name) != digest for name, digest in checks.items()):
        raise ValueError("pending approval no longer matches bundle bytes")
    approval = KDPPHistoryApproval(
        schema_version=SCHEMA_VERSION,
        model_id=MODEL_ID,
        decision="APPROVED",
        approval_token=APPROVAL_TOKEN,
        reviewer=reviewer.strip(),
        reviewed_at_utc=reviewed,
        history_manifest_sha256=checks["history_manifest_sha256"],
        history_sha256sums_sha256=checks["history_sha256sums_sha256"],
        **confirmations,
    )
    write_json(output_path, approval)
    validate_history_bundle(bundle_root, output_path)
    return approval
