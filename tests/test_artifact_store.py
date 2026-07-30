from loto.registry.artifacts import ArtifactStore


def test_artifact_store_is_content_addressed(tmp_path):
    source = tmp_path / "x.txt"
    source.write_text("hello")
    store = ArtifactStore(tmp_path / "store")
    first = store.put_file(source, namespace="run-1")
    second = store.put_file(source, namespace="run-1")
    assert first == second
    assert first["sha256"]
