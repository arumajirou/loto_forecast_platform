import hashlib
from pathlib import Path

from loto.models.artifact_store import artifact_summary


def expected_directory_hash(root: Path) -> str:
    digest = hashlib.sha256()

    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        file_digest = hashlib.sha256(path.read_bytes()).digest()

        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest)

    return digest.hexdigest()


def test_artifact_summary_for_file(tmp_path: Path) -> None:
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"model-data")

    summary = artifact_summary(artifact)

    assert summary["exists"] is True
    assert summary["artifact_type"] == "file"
    assert summary["file_count"] == 1
    assert summary["size_bytes"] == len(b"model-data")
    assert summary["sha256"] == hashlib.sha256(b"model-data").hexdigest()


def test_artifact_summary_for_directory(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "neuralforecast"
    artifact.mkdir()

    (artifact / "configuration.pkl").write_bytes(b"configuration")
    (artifact / "dataset.pkl").write_bytes(b"dataset")
    (artifact / "model.ckpt").write_bytes(b"checkpoint")

    summary = artifact_summary(artifact)

    assert summary["exists"] is True
    assert summary["artifact_type"] == "directory"
    assert summary["file_count"] == 3
    assert summary["size_bytes"] == (len(b"configuration") + len(b"dataset") + len(b"checkpoint"))
    assert summary["sha256"] == expected_directory_hash(artifact)
    assert [row["path"] for row in summary["files"]] == [
        "configuration.pkl",
        "dataset.pkl",
        "model.ckpt",
    ]


def test_artifact_summary_for_missing_path(
    tmp_path: Path,
) -> None:
    summary = artifact_summary(tmp_path / "missing")

    assert summary == {
        "exists": False,
        "artifact_type": "missing",
    }
