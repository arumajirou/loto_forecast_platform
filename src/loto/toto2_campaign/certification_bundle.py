from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

FORMAL_GAMES = ("numbers3", "numbers4", "miniloto", "loto6", "loto7")
FORMAL_CONTEXTS = (128, 256, 512)
FORMAL_HORIZONS = (1, 2, 5)
FORMAL_DEVICES = ("cpu", "cuda")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class MatrixCase:
    case_id: str
    game: str
    context: int
    horizon: int
    device: str
    request_path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def validate_lock_review(review_path: Path, lock_path: Path) -> dict[str, Any]:
    review = load_json_object(review_path)
    required = {
        "schema_version",
        "status",
        "reviewer",
        "reviewed_at",
        "lock_sha256",
        "dependency_sources_reviewed",
        "package_hashes_reviewed",
        "licenses_reviewed",
    }
    missing = sorted(required - set(review))
    if missing:
        raise ValueError(f"lock review missing fields: {missing}")
    if review["schema_version"] != 1:
        raise ValueError("lock review schema_version must be 1")
    if review["status"] != "APPROVED":
        raise ValueError("lock review status must be APPROVED")
    if not isinstance(review["reviewer"], str) or not review["reviewer"].strip():
        raise ValueError("lock review reviewer must be non-empty")
    if not isinstance(review["reviewed_at"], str) or not review["reviewed_at"].endswith("Z"):
        raise ValueError("lock review reviewed_at must be a UTC timestamp ending in Z")
    expected = review["lock_sha256"]
    if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        raise ValueError("lock review lock_sha256 must be lowercase SHA-256")
    for field in (
        "dependency_sources_reviewed",
        "package_hashes_reviewed",
        "licenses_reviewed",
    ):
        if review[field] is not True:
            raise ValueError(f"lock review field must be true: {field}")
    actual = sha256_file(lock_path)
    if actual != expected:
        raise ValueError(f"uv.lock hash mismatch: expected={expected} actual={actual}")
    return review


def _strict_sequence(value: Any, expected: tuple[Any, ...], name: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"matrix {name} must be a list")
    normalized = tuple(value)
    if normalized != expected:
        raise ValueError(f"matrix {name} must exactly equal {list(expected)}")
    return normalized


def expand_formal_matrix(manifest_path: Path, requests_root: Path) -> list[MatrixCase]:
    manifest = load_json_object(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("matrix schema_version must be 1")
    if manifest.get("matrix_id") != "toto2-4m-formal-v1":
        raise ValueError("matrix_id must be toto2-4m-formal-v1")
    games = _strict_sequence(manifest.get("games"), FORMAL_GAMES, "games")
    contexts = _strict_sequence(manifest.get("contexts"), FORMAL_CONTEXTS, "contexts")
    horizons = _strict_sequence(manifest.get("horizons"), FORMAL_HORIZONS, "horizons")
    devices = _strict_sequence(manifest.get("devices"), FORMAL_DEVICES, "devices")
    pattern = manifest.get("request_pattern")
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("request_pattern must be a non-empty string")
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        raise ValueError("request_pattern must be a safe relative path")

    cases: list[MatrixCase] = []
    seen_paths: set[Path] = set()
    for game in games:
        for context in contexts:
            for horizon in horizons:
                for device in devices:
                    case_id = f"{game}-c{context}-h{horizon}-{device}"
                    relative = Path(
                        pattern.format(
                            game=game,
                            context=context,
                            horizon=horizon,
                            device=device,
                        )
                    )
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError(f"expanded request path is unsafe: {relative}")
                    request_path = requests_root / relative
                    if request_path in seen_paths:
                        raise ValueError(f"duplicate request path: {request_path}")
                    seen_paths.add(request_path)
                    cases.append(
                        MatrixCase(
                            case_id=case_id,
                            game=game,
                            context=context,
                            horizon=horizon,
                            device=device,
                            request_path=request_path,
                        )
                    )
    if len(cases) != 90:
        raise ValueError(f"formal matrix must contain 90 cases, got {len(cases)}")
    return cases


def validate_request_case(case: MatrixCase) -> dict[str, Any]:
    request = load_json_object(case.request_path)
    geometry = request.get("game_geometry")
    if not isinstance(geometry, dict) or geometry.get("game_id") != case.game:
        raise ValueError(f"request game mismatch for {case.case_id}")
    if request.get("context_length") != case.context:
        raise ValueError(f"request context mismatch for {case.case_id}")
    if request.get("prediction_length") != case.horizon:
        raise ValueError(f"request horizon mismatch for {case.case_id}")
    if request.get("device") != case.device:
        raise ValueError(f"request device mismatch for {case.case_id}")
    if request.get("operation") != "predict":
        raise ValueError(f"request operation must be predict for {case.case_id}")
    if request.get("local_files_only") is not True:
        raise ValueError(f"request must be local_files_only for {case.case_id}")
    return request


def iter_artifact_files(root: Path, *, excluded_names: Iterable[str] = ()) -> list[Path]:
    excluded = set(excluded_names)
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in excluded and not path.is_symlink()
    ]
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def build_artifact_manifest(root: Path, *, excluded_names: Iterable[str] = ()) -> dict[str, Any]:
    entries = []
    for path in iter_artifact_files(root, excluded_names=excluded_names):
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {"schema_version": 1, "file_count": len(entries), "files": entries}


def write_sha256s(root: Path, manifest: dict[str, Any], output_path: Path) -> None:
    lines = [f"{entry['sha256']}  {entry['path']}" for entry in manifest["files"]]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_artifact_manifest(root: Path, manifest: dict[str, Any]) -> None:
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("file_count") != len(files):
        raise ValueError("artifact manifest file_count mismatch")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("artifact manifest entry must be an object")
        relative = entry.get("path")
        if not isinstance(relative, str) or relative in seen:
            raise ValueError(f"duplicate or invalid artifact path: {relative!r}")
        seen.add(relative)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"artifact is missing or unsafe: {relative}")
        if path.stat().st_size != entry.get("size_bytes"):
            raise ValueError(f"artifact size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise ValueError(f"artifact hash mismatch: {relative}")


def create_deterministic_zip(root: Path, archive_path: Path, manifest: dict[str, Any]) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in manifest["files"]:
            relative = str(entry["path"])
            data = (root / relative).read_bytes()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
