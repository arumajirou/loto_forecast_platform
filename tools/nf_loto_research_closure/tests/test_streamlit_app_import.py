import pytest


@pytest.mark.skip(reason="Streamlit アプリ本体は手動確認を想定。必要であればこの skip を外してください。")
def test_import_streamlit_app():
    # Streamlit がインストールされている前提で import が通ることだけ確認
    pytest.importorskip("streamlit")
    import streamlit_app  # noqa: F401
