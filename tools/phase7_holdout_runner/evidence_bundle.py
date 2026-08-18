from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final

EXPECTED_RUNNER_SHA256: Final = "986ea78f655ab2579bc274b00b408a71e413f3139791e13daed69cc347e88187"
EXPECTED_FREEZE_SHA256: Final = "deae004023fd1367d4bd30a6edad8b4ac687b939413c4b4ce641187664fa316c"
EXPECTED_DEVELOPMENT_SHA256: Final = "f6e0292347cd03acea95b5c788eaa51436a8b9e7e42d2fc000e9b9d366e2557e"
EXPECTED_CANONICAL_SHA256: Final = "88fd7bf24d2864fce74e95bf6475ff4b0292446f1354d403105970d095d6592f"

PHASE7_NAME: Final = "automlforecast-phase7-holdout-20260818-101611"
PHASE6C_NAME: Final = "automlforecast-phase6c-ensemble-freeze-20260818-101021"
PHASE3_NAME: Final = "automlforecast-phase3-input-size-20260817-173808"
MANIFEST_NAME: Final = "PHASE7_EVIDENCE_MANIFEST.json"
SHA256SUMS_NAME: Final = "SHA256SUMS"
CANONICAL_BUNDLE_PATH: Final = "canonical/numbers3-canonical.csv"


class EvidenceBundleError(RuntimeError):
    """Raised when portable Phase 7 evidence cannot be proven exact and safe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_pointer(pointer: Path) -> Path:
    if not pointer.is_file():
        raise EvidenceBundleError(f"canonical pointer missing: {pointer}")
    for line in pointer.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate:
            path = Path(candidate)
            if not path.is_file():
                raise EvidenceBundleError(f"canonical pointer target missing: {path}")
            return path
    raise EvidenceBundleError(f"canonical pointer is empty: {pointer}")


def require_identity(path: Path, expected: str, label: str) -> str:
    if not path.is_file():
        raise EvidenceBundleError(f"{label} missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise EvidenceBundleError(
            f"{label} SHA mismatch: expected={expected} actual={actual} path={path}"
        )
    return actual


def validate_archive_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise EvidenceBundleError(f"invalid archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceBundleError(f"unsafe archive member path: {name!r}")
    return path


def iter_tree_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def add_file(
    zf: zipfile.ZipFile,
    source: Path,
    archive_name: str,
    file_manifest: dict[str, dict[str, Any]],
) -> None:
    validate_archive_member_name(archive_name)
    digest = sha256_file(source)
    size = source.stat().st_size
    zf.write(source, archive_name)
    file_manifest[archive_name] = {"sha256": digest, "size_bytes": size}


def verify_zero_progress(progress_path: Path) -> dict[str, Any]:
    if not progress_path.is_file():
        raise EvidenceBundleError(f"original Phase7 progress missing: {progress_path}")
    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceBundleError("original progress root must be an object")
    state = payload.get("state", payload.get("phase"))
    if state != "REPLAY_VERIFICATION":
        raise EvidenceBundleError(f"unexpected original Phase7 state: {state!r}")
    if int(payload.get("holdout_draws_done", 0)) != 0:
        raise EvidenceBundleError("original Holdout draws are nonzero")
    if int(payload.get("actuals_accessed", 0)) != 0:
        raise EvidenceBundleError("original actual accesses are nonzero")
    lock_root = progress_path.parent / "prediction_locks"
    if lock_root.exists() and any(path.is_file() for path in lock_root.rglob("*")):
        raise EvidenceBundleError("original Phase7 prediction locks already exist")
    return payload


def export_bundle(*, downloads: Path, output: Path) -> dict[str, Any]:
    phase7 = downloads / PHASE7_NAME
    phase6c = downloads / PHASE6C_NAME
    phase3 = downloads / PHASE3_NAME
    pointer = downloads / "numbers3-current-canonical-path.txt"

    runner = phase7 / "phase7_holdout.py"
    progress = phase7 / "artifacts" / "progress.json"
    freeze = phase6c / "artifacts" / "CANDIDATE_FREEZE.json"
    frozen_evidence = phase6c / "artifacts" / "frozen_component_evidence"
    development = phase3 / "artifacts" / "numbers3-development-only.csv"
    canonical = resolve_pointer(pointer)

    require_identity(runner, EXPECTED_RUNNER_SHA256, "sealed original runner")
    require_identity(freeze, EXPECTED_FREEZE_SHA256, "Candidate Freeze")
    require_identity(development, EXPECTED_DEVELOPMENT_SHA256, "Development")
    require_identity(canonical, EXPECTED_CANONICAL_SHA256, "canonical data")
    verify_zero_progress(progress)
    if not frozen_evidence.is_dir():
        raise EvidenceBundleError(f"frozen component evidence missing: {frozen_evidence}")

    output = output.resolve()
    if output.exists():
        raise EvidenceBundleError(f"refusing to overwrite existing bundle: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    file_manifest: dict[str, dict[str, Any]] = {}
    manifest: dict[str, Any] = {
        "schema_version": "phase7-portable-evidence-bundle/v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_downloads": str(downloads.resolve()),
        "scientific_identities": {
            "sealed_original_runner_sha256": EXPECTED_RUNNER_SHA256,
            "candidate_freeze_sha256": EXPECTED_FREEZE_SHA256,
            "development_sha256": EXPECTED_DEVELOPMENT_SHA256,
            "canonical_sha256": EXPECTED_CANONICAL_SHA256,
        },
        "original_phase7_state": "REPLAY_VERIFICATION",
        "holdout_draws_accessed": 0,
        "actuals_accessed": 0,
        "prediction_lock_created": False,
        "files": file_manifest,
    }

    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        add_file(zf, runner, f"{PHASE7_NAME}/phase7_holdout.py", file_manifest)
        add_file(zf, progress, f"{PHASE7_NAME}/artifacts/progress.json", file_manifest)
        add_file(zf, development, f"{PHASE3_NAME}/artifacts/numbers3-development-only.csv", file_manifest)
        add_file(zf, canonical, CANONICAL_BUNDLE_PATH, file_manifest)

        for source in iter_tree_files(phase6c):
            relative = source.relative_to(phase6c).as_posix()
            add_file(zf, source, f"{PHASE6C_NAME}/{relative}", file_manifest)

        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        zf.writestr(MANIFEST_NAME, manifest_bytes)
        sums = "".join(
            f"{metadata['sha256']}  {name}\n" for name, metadata in sorted(file_manifest.items())
        )
        sums += f"{hashlib.sha256(manifest_bytes).hexdigest()}  {MANIFEST_NAME}\n"
        zf.writestr(SHA256SUMS_NAME, sums.encode("ascii"))

    result = {
        "status": "PASS",
        "bundle": str(output),
        "bundle_sha256": sha256_file(output),
        "file_count": len(file_manifest),
        "holdout_executed": False,
        "actuals_accessed": 0,
    }
    return result


def load_manifest_from_zip(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        payload = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except KeyError as exc:
        raise EvidenceBundleError(f"bundle manifest missing: {MANIFEST_NAME}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != "phase7-portable-evidence-bundle/v1":
        raise EvidenceBundleError("unsupported or invalid evidence bundle manifest")
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise EvidenceBundleError("bundle manifest files map is missing or empty")
    return payload


def verify_manifest_identities(manifest: dict[str, Any]) -> None:
    identities = manifest.get("scientific_identities")
    if not isinstance(identities, dict):
        raise EvidenceBundleError("scientific identities missing from manifest")
    expected = {
        "sealed_original_runner_sha256": EXPECTED_RUNNER_SHA256,
        "candidate_freeze_sha256": EXPECTED_FREEZE_SHA256,
        "development_sha256": EXPECTED_DEVELOPMENT_SHA256,
        "canonical_sha256": EXPECTED_CANONICAL_SHA256,
    }
    if identities != expected:
        raise EvidenceBundleError(f"scientific identity manifest mismatch: {identities!r}")
    if manifest.get("original_phase7_state") != "REPLAY_VERIFICATION":
        raise EvidenceBundleError("bundle original Phase7 state is not REPLAY_VERIFICATION")
    if int(manifest.get("holdout_draws_accessed", -1)) != 0:
        raise EvidenceBundleError("bundle reports nonzero Holdout access")
    if int(manifest.get("actuals_accessed", -1)) != 0:
        raise EvidenceBundleError("bundle reports nonzero actual access")
    if manifest.get("prediction_lock_created") is not False:
        raise EvidenceBundleError("bundle reports a prediction lock")


def import_bundle(*, bundle: Path, target: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    target = target.resolve()
    if not bundle.is_file():
        raise EvidenceBundleError(f"bundle missing: {bundle}")

    with zipfile.ZipFile(bundle, "r") as zf:
        names = zf.namelist()
        for name in names:
            validate_archive_member_name(name)
        manifest = load_manifest_from_zip(zf)
        verify_manifest_identities(manifest)
        files = manifest["files"]
        assert isinstance(files, dict)

        expected_names = set(files) | {MANIFEST_NAME, SHA256SUMS_NAME}
        unexpected = set(names) - expected_names
        missing = expected_names - set(names)
        if unexpected or missing:
            raise EvidenceBundleError(
                f"bundle member set mismatch: unexpected={sorted(unexpected)} missing={sorted(missing)}"
            )

        for name, metadata in files.items():
            validate_archive_member_name(name)
            if not isinstance(metadata, dict):
                raise EvidenceBundleError(f"invalid manifest metadata for {name}")
            data = zf.read(name)
            actual_sha = hashlib.sha256(data).hexdigest()
            expected_sha = str(metadata.get("sha256", ""))
            if actual_sha != expected_sha:
                raise EvidenceBundleError(
                    f"archive member SHA mismatch: path={name} expected={expected_sha} actual={actual_sha}"
                )
            if len(data) != int(metadata.get("size_bytes", -1)):
                raise EvidenceBundleError(f"archive member size mismatch: {name}")

        if target.exists():
            sentinel = target / MANIFEST_NAME
            if sentinel.is_file():
                existing = json.loads(sentinel.read_text(encoding="utf-8"))
                if existing == manifest:
                    return {
                        "status": "PASS_ALREADY_IMPORTED",
                        "target": str(target),
                        "bundle_sha256": sha256_file(bundle),
                        "file_count": len(files),
                    }
            raise EvidenceBundleError(f"refusing to overwrite existing evidence root: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.import-", dir=target.parent))
        try:
            for name in sorted(files):
                destination = temp.joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name, "r") as source, destination.open("wb") as handle:
                    shutil.copyfileobj(source, handle)

            canonical = temp.joinpath(*PurePosixPath(CANONICAL_BUNDLE_PATH).parts)
            pointer = temp / "numbers3-current-canonical-path.txt"
            pointer.write_text(str((target / CANONICAL_BUNDLE_PATH).resolve()) + "\n", encoding="utf-8")
            (temp / MANIFEST_NAME).write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

            require_identity(temp / PHASE7_NAME / "phase7_holdout.py", EXPECTED_RUNNER_SHA256, "sealed original runner")
            require_identity(
                temp / PHASE6C_NAME / "artifacts" / "CANDIDATE_FREEZE.json",
                EXPECTED_FREEZE_SHA256,
                "Candidate Freeze",
            )
            require_identity(
                temp / PHASE3_NAME / "artifacts" / "numbers3-development-only.csv",
                EXPECTED_DEVELOPMENT_SHA256,
                "Development",
            )
            require_identity(canonical, EXPECTED_CANONICAL_SHA256, "canonical data")
            verify_zero_progress(temp / PHASE7_NAME / "artifacts" / "progress.json")

            sums_lines = []
            for path in sorted(p for p in temp.rglob("*") if p.is_file() and p.name != SHA256SUMS_NAME):
                sums_lines.append(f"{sha256_file(path)}  {path.relative_to(temp).as_posix()}\n")
            (temp / SHA256SUMS_NAME).write_text("".join(sums_lines), encoding="ascii")

            os.replace(temp, target)
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise

    return {
        "status": "PASS",
        "target": str(target),
        "bundle_sha256": sha256_file(bundle),
        "file_count": len(files),
    }


def default_export_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Downloads" / f"phase7-portable-evidence-v1-{stamp}.zip"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export/import exact portable Phase 7 evidence bundles.")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export")
    export.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    export.add_argument("--output", type=Path, default=None)

    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("--bundle", type=Path, required=True)
    import_cmd.add_argument("--target", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "export":
        result = export_bundle(downloads=args.downloads.resolve(), output=(args.output or default_export_path()))
        print(f"EVIDENCE_BUNDLE={result['bundle']}")
        print(f"EVIDENCE_BUNDLE_SHA256={result['bundle_sha256']}")
        print(f"EVIDENCE_FILE_COUNT={result['file_count']}")
        print("HOLDOUT_EXECUTED=NO")
        print("ACTUALS_ACCESSED=0")
        print("STATUS=PASS")
        return 0

    result = import_bundle(bundle=args.bundle, target=args.target)
    print(f"EVIDENCE_ROOT={result['target']}")
    print(f"EVIDENCE_BUNDLE_SHA256={result['bundle_sha256']}")
    print(f"EVIDENCE_FILE_COUNT={result['file_count']}")
    print("HOLDOUT_EXECUTED=NO")
    print("ACTUALS_ACCESSED=0")
    print(f"STATUS={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
