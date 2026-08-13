from loto.sklearn_provider.runner import certify_estimator, create_estimator


def test_core_regressor_smoke() -> None:
    result = certify_estimator("LinearRegression", seed=1)
    assert result.status == "VERIFIED"
    assert result.kind == "regressor"
    assert "mae" in result.metrics
    assert "hit_at_plus_minus_1" in result.metrics


def test_core_classifier_smoke() -> None:
    result = certify_estimator("LogisticRegression", seed=1)
    assert result.status == "VERIFIED"
    assert result.kind == "classifier"
    assert "accuracy" in result.metrics


def test_required_meta_estimator_is_constructible() -> None:
    estimator = create_estimator("GridSearchCV", seed=1)
    assert estimator.estimator is not None


def test_seed_is_forwarded_to_estimators() -> None:
    estimator = create_estimator("RandomForestRegressor", seed=7)
    assert estimator.random_state == 7
