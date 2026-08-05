from __future__ import annotations

import hashlib
from pathlib import Path

PACKAGE_VERSION = "0.1.1"
WHEEL_SHA256 = "1d9f0ead93662d4438371ef0bb3b6319dc4811ba9d17fe343c8fa8f456b1730b"
SDIST_SHA256 = "bc82b6e0698b9828888cd6e5037717dba8e107320116725061824308e10fbeb2"
SOURCE_ATTESTATION_COMMIT = "abdf2898162482cc5c862905a406fc1134fbae67"
SOURCE_ACCESS_STATUS = "PYPI_ATTESTED_NOT_FULLY_PUBLICLY_AUDITABLE"
MODEL_WEIGHT_SHA256 = "184b160ffbe4c01a26beeba14015ff3507c7497e1f3577114187bbc1d19fcac1"
MODEL_CONFIG_SHA256 = "cddbe6d0be4919cb7b0cad747fb19a295264e129d1c0790cf62133b4cb5da727"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_snapshot(
    snapshot_path: Path, trusted_cache_roots: list[Path]
) -> tuple[Path, Path]:
    resolved = snapshot_path.expanduser().resolve(strict=True)
    roots = [root.expanduser().resolve(strict=True) for root in trusted_cache_roots]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError("snapshot_path is outside trusted cache roots")
    config_path = resolved / "model-config.yaml"
    weight_path = resolved / "model.ckpt"
    if not config_path.is_file() or not weight_path.is_file():
        raise FileNotFoundError("trusted snapshot requires model-config.yaml and model.ckpt")
    if sha256_file(config_path) != MODEL_CONFIG_SHA256:
        raise ValueError("model config SHA-256 mismatch")
    if sha256_file(weight_path) != MODEL_WEIGHT_SHA256:
        raise ValueError("model weight SHA-256 mismatch")
    return weight_path, config_path
