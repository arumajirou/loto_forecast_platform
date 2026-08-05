"""Build immutable expectations from a verified registry receipt."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from .persistence import sha256_file
from .prospective_registry_contract import (
    BACKEND_RECEIPTS,
    REGISTRY_PAYLOAD,
    REGISTRY_REPORT,
    _canonical_sha256,
    _read_json,
)
from .prospective_registry_payload import (
    _candidate_frame,
    _position_metric_frame,
    _read_registry_tables,
    _seed_metric_frame,
)


def _copy_tree_exact(source: Path, target: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"registry receipt must be a regular directory: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "registry receipt contains a symlink: "
                f"{path.relative_to(source).as_posix()}"
            )
    shutil.copytree(source, target)
    source_files = {
        path.relative_to(source).as_posix(): sha256_file(path)
        for path in source.rglob("*")
        if path.is_file()
    }
    target_files = {
        path.relative_to(target).as_posix(): sha256_file(path)
        for path in target.rglob("*")
        if path.is_file()
    }
    if source_files != target_files:
        raise RuntimeError("registry receipt copy differs from source")
    return {
        "path": target.name,
        "file_count": len(target_files),
        "tree_sha256": _canonical_sha256(target_files),
    }


def _expected_artifacts(receipt_root: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    scoring_manifest = _read_json(
        receipt_root / "source_evidence" / "ARTIFACT_MANIFEST.json",
        "copied scoring artifact manifest",
    )
    records = scoring_manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("copied scoring artifact manifest file inventory is missing")
    rows: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, Mapping):
            raise ValueError("copied scoring artifact inventory record is invalid")
        path = str(item.get("path") or "")
        rows[path] = {
            "registry_id": payload["registry_id"],
            "path": path,
            "size_bytes": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
        }
    for name in (
        "ARTIFACT_MANIFEST.json",
        "SCORING_REPORT.json",
        "ACTUALS_LOCK.json",
        "SHA256SUMS",
    ):
        source = receipt_root / "source_evidence" / name
        rows[name] = {
            "registry_id": payload["registry_id"],
            "path": name,
            "size_bytes": source.stat().st_size,
            "sha256": sha256_file(source),
        }
    return [rows[name] for name in sorted(rows)]


def _expected_snapshot(receipt_root: Path) -> dict[str, Any]:
    payload = _read_json(receipt_root / REGISTRY_PAYLOAD, "registry payload")
    report = _read_json(receipt_root / REGISTRY_REPORT, "registry report")
    backend_receipts = _read_json(
        receipt_root / BACKEND_RECEIPTS,
        "backend receipts",
    )
    receipts = backend_receipts.get("receipts")
    if not isinstance(receipts, dict):
        raise ValueError("backend receipts.receipts must be an object")
    if report.get("status") != "PASS":
        raise ValueError("only PASS registry receipts can be formally reconciled")
    tables = _read_registry_tables(receipt_root / "source_evidence")
    registry_id = str(payload["registry_id"])
    candidates = _candidate_frame(
        tables["seed_summary"],
        tables["ranking"],
        registry_id,
    )
    seed_metrics = _seed_metric_frame(
        tables["seed_metrics"],
        registry_id,
    )
    position_metrics = _position_metric_frame(
        tables["position_metrics"],
        registry_id,
    )
    artifacts = pd.DataFrame(_expected_artifacts(receipt_root, payload))
    mlflow_receipt = receipts.get("mlflow")
    postgres_finalize = receipts.get("postgres_finalize")
    if not isinstance(mlflow_receipt, dict) or not isinstance(postgres_finalize, dict):
        raise ValueError("PASS registry receipt lacks finalized backend receipts")
    parent_run_id = str(mlflow_receipt.get("parent_run_id") or "")
    if not parent_run_id:
        raise ValueErroŠ“S›İÈ\™[[ˆQ\ÈZ\ÜÚ[™Èœ›ÛH™YÚ\İH™XÙZ\ŠBˆYˆÜİÜ™\×Ùš[˜[^™K™Ù]
›[›İ×Ü\™[Ü[—ÚYŠHOH\™[Ü[—ÚY‚ˆ˜Z\ÙH˜[YQ\œ›â‚'&V6V—B÷7Fw&U5ÂæBÔÆfÆ÷r&VçB'Vâ”G2F–ffW""¢&6¶VæE÷öÆ–7’Ò–ÆöBævWB‚&&6¶VæE÷öÆ–7’"¢–bæ÷B—6–ç7Fæ6R†&6¶VæE÷öÆ–7’ÂF–7B“ ¢&—6RfÇVTTW'&÷"‚'&Vv—7G'’–ÆöB&6¶VæBöÆ–7’—2Ö—76–ær"¢ÖÆfÆ÷uö'F–f7G2Ò°¢°¢'F‚#¢'&Vv—7G'•öWf–FVæ6Rõ$Tt•5E%•õ”ÄôBæ§6öâ"À¢'6†#Sb#¢6†#Seöf–ÆR‡&V6V—E÷&ö÷Bò$Tt•5E%•õ”ÄôB’À¢ÒÀ¢°¢'F‚#¢€¢'&Vv—7G'•öWf–FVæ6R÷6÷W&6UöWf–FVæ6Rò ¢$%D”d5EôÔä”dU5Bæ§6öâ ¢’À¢'6†#Sb#¢6†#Seöf–ÆR€¢&V6V—E÷&ö÷Bò'6÷W&6UöWf–FVæ6R"ò$%D”d5EôÔä”dU5Bæ§6öâ ¢’À¢ÒÀ¢Ğ¢–b&6¶VæE÷öÆ–7’ævWB‚&'F–f7EöÖöFR"’ÓÒ&gVÆÂ# ¢ÖÆfÆ÷uö'F–f7G2æVæB€¢°¢'F‚#¢'66÷&–æuö'F–f7Bõ44õ$”äuõ$Uõ%Bæ§6öâ"À¢'6†#Sb#¢6†#Seöf–ÆR€¢&V6V—E÷&ö÷Bò'6÷W&6UöWf–FVæ6R"ò%44õ$”äuõ$Uõ%Bæ§6öâ ¢’À¢Ğ¢¢W‡V7FVBÒ°¢'66†VÖ÷fW'6–öâ#¢$T4ôä4”Ä”D”ôåõ44„TÔõdU%4”ôâÀ¢'&Vv—7G'•ö–B#¢&Vv—7G'•ö–BÀ¢'&Vv—7G'•öæÖW76R#¢–ÆöE²'&Vv—7G'•öæÖW76R%ÒÀ¢'66÷&–æuö–B#¢–ÆöE²'66÷&–æuö–B%ÒÀ¢'–ÆöE÷6†#Sb#¢–ÆöE²'–ÆöE÷6†#Sb%ÒÀ¢&7&VFVEöB#¢–ÆöE²&7&VFVEöB%ÒÀ¢'6÷W&6R#¢–ÆöE²'6÷W&6R%ÒÀ¢&6÷VçG2#¢–ÆöE²&6÷VçG2%ÒÀ¢&&6¶VæE÷öÆ–7’#¢&6¶VæE÷öÆ–7’À¢'&V6V—EöÖÆfÆ÷u÷&VçE÷'Våö–B#¢&VçE÷'Våö–BÀ¢&6æF–FFW2#¢6æF–FFW2çFõöF–7B†÷&–VçCÒ'&V6÷&G2"’À¢'6VVEöÖWG&–72#¢6VVEöÖWG&–72çFõöF–7B†÷&–VçCÒ'&V6÷&G2"’À¢'÷6—F–öåöÖWG&–72#¢÷6—F–öåöÖWG&–72çFõöF–7B†÷&–VçCÒ'&V6÷&G2"’À¢&'F–f7G2#¢'F–f7G2çFõöF–7B†÷&–VçCÒ'&V6÷&G2"’À¢&ÖÆfÆ÷uö'F–f7G2#¢ÖÆfÆ÷uö'F–f7G2À¢Ğ¢W‡V7FVE²&W‡V7FVE÷6†#Sb%ÒÒö6æöæ–6Å÷6†#Sb†W‡V7FVB¢&WGW&âW‡V7FV@ 