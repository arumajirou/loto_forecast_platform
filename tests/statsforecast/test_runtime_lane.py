from __future__ import annotations

import hashlib
import io
import json

from packaging.tags import Tag

from loto.statsforecast.runtime_lane import (
    fetch_release_artifact,
    select_compatible_release_file,
    verify_portable_sha256sums,
)


def _release_payload(artifact: bytes) -> dict:
    digest = hashlib.sha256(artifact).hexdigest()
    return {
        "info": {"version": "2.1.1"},
        "urls": [
            {
                "filename": "statsforecast-2.1.1.tar.gz",
                "packagetype": "sdist",
                "url": "https://example.invalid/source",
                "digests": {"sha256": "1" * 64},
                "size": 1,
            },
            {
                "filename": (
                    "statsforecast-2.1.1-cp313-cp313-"
                    "manylinux_2_28_x86_64.whl"
                ),
                "packagetype": "bdist_wheel",
                "url": "https://example.invalid/wheel",
                "digests": {"sha256": digest},
                "size": len(artifact),
            },
        ],
    }


def test_selects_compatible_cp313_wheel() -> None:
    artifact = b"wheel-bytes"
    selected = select_compatible_release_file(
        _release_payload(artifact),
        supported_tags=[
            Tag("cp313", "cp313", "manylinux_2_28_x86_64")
        ],
    )
    assert selected["packagetype"] == "bdist_wheel"
    assert selected["filename"].endswith("x86_64.whl")


def test_fetch_verifies_pypi_digest_and_writes_portable_sums(
    tmp_path,
) -> None:
    artifact = b"wheel-bytes"
    metadata = json.dumps(_release_payload(artifact)).encode()

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def opener(url, timeout):
        assert timeout > 0
        return Response(
            metadata if str(url).endswith("/json") else artifact
        )

    path = fetch_release_artifact(
        tmp_path,
        opener=opener,
        supported_tags=[
            Tag("cp313", "cp313", "manylinux_2_28_x86_64")
        ],
    )
    assert path.read_bytes() == artifact
    assert verify_portable_sha256sums(tmp_path)["status"] == "PASS"


def test_checksum_verifier_rejects_parent_traversal(tmp_path) -> None:
    (tmp_path / "SHA256SUMS").write_text(
        f"{'0' * 64}  ../outside\n",
        encoding="utf-8",
    )
    report = verify_portable_sha256sums(tmp_path)
    assert report["status"] == "FAILED"
    assert any("unsafe path" in failure for failure in report["failures"])


def test_checksum_verifier_detects_tampering(tmp_path) -> None:
    target = tmp_path / "result.json"
    target.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (tmp_path / "SHA256SUMS").write_text(
        f"{digest}  result.json\n",
        encoding="utf-8",
    )
    assert verify_portable_sha256sums(tmp_path)["status"] == "PASS"
    target.write_text('{"tampered":true}\n', encoding="utf-8")
    assert verify_portable_sha256sums(tmp_path)["status"] == "FAILED"
