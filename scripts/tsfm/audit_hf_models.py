#!/usr/bin/env python3
"""Audit pinned Hugging Face TSFM repositories without downloading model weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, ModelCard
from huggingface_hub.errors import HfHubHTTPError

FULL_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

WEIGHT_SUFFIXES = (
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".ckpt",
    ".onnx",
    ".h5",
    ".msgpack",
    ".gguf",
)

CUSTOM_CODE_FILENAMES = {
    "configuration.py",
    "modeling.py",
    "processing.py",
    "tokenization.py",
}

LICENSE_REVIEW_REQUIRED = {
    "",
    "unknown",
    "other",
    "custom",
    "license",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pins = data.get("pins")

    if not isinstance(pins, list) or not pins:
        raise ValueError("manifest must contain a non-empty pins array")

    normalized: list[dict[str, str]] = []

    for index, pin in enumerate(pins):
        if not isinstance(pin, dict):
            raise ValueError(f"pin {index} must be an object")

        row = {
            "model_id": str(pin.get("model_id", "")).strip(),
            "repo_id": str(pin.get("repo_id", "")).strip(),
            "revision": str(pin.get("revision", "")).strip().lower(),
        }

        if not row["model_id"] or not row["repo_id"]:
            raise ValueError(f"pin {index} is missing model_id or repo_id")

        if not FULL_COMMIT_RE.fullmatch(row["revision"]):
            raise ValueError(f"pin {index} has invalid full revision: {row['revision']!r}")

        normalized.append(row)

    return normalized


def sibling_size(sibling: Any) -> int:
    size = getattr(sibling, "size", None)
    if isinstance(size, int) and size >= 0:
        return size

    lfs = getattr(sibling, "lfs", None)

    if isinstance(lfs, dict):
        lfs_size = lfs.get("size")
    else:
        lfs_size = getattr(lfs, "size", None)

    if isinstance(lfs_size, int) and lfs_size >= 0:
        return lfs_size

    return 0


def metadata_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return converted

    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return {key: item for key, item in raw.items() if not key.startswith("_")}

    return {}


def extract_card_metadata(
    repo_id: str,
    revision: str,
) -> tuple[dict[str, Any], str]:
    try:
        card = ModelCard.load(repo_id, revision=revision)
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"

    raw_metadata = metadata_to_dict(getattr(card, "data", None))
    metadata: dict[str, Any] = {}

    for key in (
        "license",
        "license_name",
        "license_link",
        "library_name",
        "pipeline_tag",
        "base_model",
        "datasets",
        "language",
        "tags",
    ):
        value = raw_metadata.get(key)
        if value not in (None, "", [], {}):
            metadata[key] = value

    return metadata, ""


def classify_license(metadata: dict[str, Any]) -> str:
    license_value = str(metadata.get("license", "") or "").strip().lower()

    if license_value in LICENSE_REVIEW_REQUIRED:
        return "MANUAL_REVIEW_REQUIRED"

    return "DECLARED_REVIEW_REQUIRED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--verified-at")
    args = parser.parse_args()

    pins = load_manifest(args.manifest)

    if args.verified_at:
        try:
            parsed = datetime.fromisoformat(args.verified_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SystemExit(f"BLOCKED: invalid --verified-at: {exc}") from exc

        if parsed.tzinfo is None:
            raise SystemExit("BLOCKED: --verified-at must contain a timezone")

        verified_at = parsed.astimezone(UTC).isoformat()
    else:
        verified_at = datetime.now(UTC).isoformat()

    api = HfApi()
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for pin in pins:
        model_id = pin["model_id"]
        repo_id = pin["repo_id"]
        revision = pin["revision"]

        try:
            info = api.model_info(
                repo_id=repo_id,
                revision=revision,
                files_metadata=True,
            )
        except HfHubHTTPError as exc:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        except Exception as exc:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        resolved_repo_id = str(getattr(info, "id", "") or "")
        resolved_sha = str(getattr(info, "sha", "") or "").lower()

        if resolved_repo_id.lower() != repo_id.lower():
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": (f"repository mismatch: API returned {resolved_repo_id!r}"),
                }
            )
            continue

        if resolved_sha != revision:
            errors.append(
                {
                    "model_id": model_id,
                    "repo_id": repo_id,
                    "error": (f"revision mismatch: expected={revision}, actual={resolved_sha}"),
                }
            )
            continue

        siblings = list(getattr(info, "siblings", None) or [])
        files: list[dict[str, Any]] = []
        suffix_counts: Counter[str] = Counter()

        total_known_bytes = 0
        weight_known_bytes = 0
        weight_files: list[str] = []
        python_files: list[str] = []

        for sibling in siblings:
            filename = str(getattr(sibling, "rfilename", "") or "")
            size = sibling_size(sibling)
            suffix = Path(filename).suffix.lower()

            total_known_bytes += size
            suffix_counts[suffix or "<none>"] += 1

            is_weight = filename.lower().endswith(WEIGHT_SUFFIXES)
            if is_weight:
                weight_files.append(filename)
                weight_known_bytes += size

            if suffix == ".py":
                python_files.append(filename)

            files.append(
                {
                    "path": filename,
                    "size_bytes": size,
                    "is_weight": is_weight,
                }
            )

        config = getattr(info, "config", None)
        config_dict = config if isinstance(config, dict) else {}

        auto_map = config_dict.get("auto_map")
        architectures = config_dict.get("architectures")

        custom_code_markers = sorted(
            filename
            for filename in python_files
            if (
                Path(filename).name in CUSTOM_CODE_FILENAMES
                or filename.startswith("modeling_")
                or filename.startswith("configuration_")
            )
        )

        trust_remote_code_candidate = bool(auto_map or custom_code_markers)

        card_metadata, card_error = extract_card_metadata(
            repo_id,
            revision,
        )

        license_value = card_metadata.get("license")
        if not license_value:
            info_card_metadata = metadata_to_dict(getattr(info, "card_data", None))
            license_value = info_card_metadata.get("license")

            if license_value:
                card_metadata["license"] = license_value

            for key in (
                "license_name",
                "license_link",
                "library_name",
                "pipeline_tag",
                "base_model",
                "datasets",
                "language",
                "tags",
            ):
                value = info_card_metadata.get(key)
                if key not in card_metadata and value not in (None, "", [], {}):
                    card_metadata[key] = value

        used_storage = getattr(info, "used_storage", None)
        if not isinstance(used_storage, int):
            used_storage = None

        stored_weights_within_16gb = weight_known_bytes > 0 and weight_known_bytes <= 16 * 1024**3

        gated_value = getattr(info, "gated", False)
        gated_required = gated_value not in (False, None, "")

        results.append(
            {
                "model_id": model_id,
                "repo_id": repo_id,
                "revision": revision,
                "verified_at": verified_at,
                "private": bool(getattr(info, "private", False)),
                "gated": gated_value,
                "gated_required": gated_required,
                "disabled": bool(getattr(info, "disabled", False)),
                "library_name": getattr(info, "library_name", None),
                "pipeline_tag": getattr(info, "pipeline_tag", None),
                "tags": list(getattr(info, "tags", None) or []),
                "card_metadata": card_metadata,
                "card_error": card_error,
                "license_status": classify_license(card_metadata),
                "file_count": len(files),
                "known_file_bytes": total_known_bytes,
                "hub_used_storage_bytes": used_storage,
                "weight_file_count": len(weight_files),
                "known_weight_bytes": weight_known_bytes,
                "weight_files": sorted(weight_files),
                "file_suffix_counts": dict(sorted(suffix_counts.items())),
                "python_files": sorted(python_files),
                "custom_code_markers": custom_code_markers,
                "config_auto_map": auto_map,
                "config_architectures": architectures,
                "trust_remote_code_candidate": (trust_remote_code_candidate),
                "has_safetensors": any(name.endswith(".safetensors") for name in weight_files),
                "has_pytorch_bin": any(name.endswith(".bin") for name in weight_files),
                "has_gguf": any(name.endswith(".gguf") for name in weight_files),
                "stored_weight_bytes": weight_known_bytes,
                "stored_weights_within_16gb": (stored_weights_within_16gb),
                "runtime_vram_certified": False,
                "files": files,
                "source": (f"https://huggingface.co/{repo_id}/tree/{revision}"),
            }
        )

    status = "PASS" if not errors and len(results) == len(pins) else "BLOCKED"

    output = {
        "schema_version": 1,
        "status": status,
        "generated_at": verified_at,
        "manifest": str(args.manifest),
        "manifest_sha256": sha256_file(args.manifest),
        "expected_models": len(pins),
        "audited_models": len(results),
        "failed_models": len(errors),
        "results": sorted(
            results,
            key=lambda row: row["model_id"],
        ),
        "errors": errors,
    }
    write_json(args.output, output)

    summary = {
        "schema_version": 1,
        "status": status,
        "generated_at": verified_at,
        "expected_models": len(pins),
        "audited_models": len(results),
        "failed_models": len(errors),
        "private_models": sum(row["private"] for row in results),
        "gated_models": sum(row["gated_required"] for row in results),
        "disabled_models": sum(row["disabled"] for row in results),
        "trust_remote_code_candidates": sum(row["trust_remote_code_candidate"] for row in results),
        "models_with_safetensors": sum(row["has_safetensors"] for row in results),
        "models_with_gguf": sum(row["has_gguf"] for row in results),
        "stored_weights_within_16gb": sum(row["stored_weights_within_16gb"] for row in results),
        "runtime_vram_certified_models": sum(row["runtime_vram_certified"] for row in results),
        "license_status_counts": dict(Counter(row["license_status"] for row in results)),
        "errors": errors,
    }
    write_json(args.summary, summary)

    print(
        json.dumps(
            {
                "status": status,
                "expected": len(pins),
                "audited": len(results),
                "failed": len(errors),
                "output": str(args.output),
                "output_sha256": sha256_file(args.output),
                "summary": str(args.summary),
                "summary_sha256": sha256_file(args.summary),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
