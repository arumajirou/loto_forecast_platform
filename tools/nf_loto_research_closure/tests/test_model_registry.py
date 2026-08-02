from src.ml import model_registry as mr


def test_list_automodel_names_contains_basic_models():
    names = mr.list_automodel_names()
    # 代表的な AutoModel が含まれていること
    assert "AutoTFT" in names
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)


def test_get_model_spec_returns_dataclass():
    spec = mr.get_model_spec("AutoTFT")
    assert spec is not None
    assert spec.name == "AutoTFT"
    assert hasattr(spec, "family")
    assert hasattr(spec, "exogenous")
    assert hasattr(spec.exogenous, "futr")
