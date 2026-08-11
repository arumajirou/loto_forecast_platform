from types import SimpleNamespace

from loto.neuralforecast.training_worker_evidence import (
    TrainingWorkerEvidenceMixin,
    restore_official_auto_class,
    training_evidence_auto_class,
)


def test_evidence_wrapper_restores_official_class_after_complete_fit() -> None:
    class AutoModel:
        def fit(self, *args, **kwargs):
            self.model = SimpleNamespace(
                training_runtime_evidence={"schema_version": "1.0.0", "status": "PASS"}
            )
            return self

    instrumented = training_evidence_auto_class(AutoModel)
    model = AutoModel()
    model.__class__ = instrumented

    assert isinstance(model, TrainingWorkerEvidenceMixin)
    result = model.fit()

    assert result is model
    assert type(model) is AutoModel
    assert type(model).__name__ == "AutoModel"
    assert model.model.training_runtime_evidence["status"] == "PASS"


def test_restore_official_auto_class_is_idempotent_for_plain_model() -> None:
    class AutoModel:
        pass

    model = AutoModel()
    assert restore_official_auto_class(model) is model
    assert type(model) is AutoModel
