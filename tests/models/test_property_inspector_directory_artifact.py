import hashlib
from pathlib import Path

from loto.models.catalog import ModelSpec
from loto.models.property_inspector import (
    inspect_model_properties,
)


def test_directory_artifact_properties(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "neuralforecast"
    artifact.mkdir()

    checkpoint = artifact / "model.ckpt"
    checkpoint.write_bytes(b"checkpoint")

    spec = ModelSpec(
        model_id="nf-auto-test",
        family="neuralforecast_auto",
        library="neuralforecast_auto",
        class_name="AutoDLinear",
        package="neuralforecast",
        task="position_series",
        capabilities=("gpu", "checkpoint"),
    )

    properties = inspect_model_properties(
        spec,
        model=None,
        params={"seed": 42},
        artifact_path=artifact,
        device="cpu",
        precision="32",
    )

    expected = hashlib.sha256()
    expected.update(b"model.ckpt")
    expected.update(b"\0")
    expected.update(hashlib.sha256(b"checkpoint").digest())

    assert properties["artifact_type"] == "directory"
    assert properties["artifact_file_count"] == 1
    assert properties["model_file_size"] == len(b"checkpoint")
    assert properties["model_sha256"] == (expected.hexdigest())
