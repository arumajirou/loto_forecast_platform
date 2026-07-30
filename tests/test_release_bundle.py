from loto.registry.release import create_release_bundle, verify_release_bundle


def test_release_bundle_detects_artifact_change(tmp_path):
    artifact = tmp_path / "forecast.json"
    artifact.write_text('{"x":1}')
    bundle = create_release_bundle("release-1", [artifact], tmp_path / "release.json")
    assert verify_release_bundle(bundle)
    artifact.write_text('{"x":2}')
    assert not verify_release_bundle(bundle)
