from loto.sklearn_provider.inventory import discover_estimators


def test_inventory_is_dynamic_and_contains_core_models() -> None:
    names = {record.name for record in discover_estimators()}
    assert "LinearRegression" in names
    assert "LogisticRegression" in names
    assert "RandomForestRegressor" in names
    assert "RandomForestClassifier" in names


def test_kind_filters() -> None:
    classifiers = {record.name for record in discover_estimators("classifier")}
    regressors = {record.name for record in discover_estimators("regressor")}
    assert "LogisticRegression" in classifiers
    assert "Ridge" in regressors
