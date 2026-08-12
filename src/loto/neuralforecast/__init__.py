"""Database-backed NeuralForecast execution services."""

from loto.neuralforecast import db_automodel as _db_automodel
from loto.neuralforecast import db_automodel_facade as _db_automodel_facade
from loto.neuralforecast.db_training_evidence_facade import install as _install_db_training_evidence

_db_automodel_facade.install(_db_automodel)
_install_db_training_evidence(_db_automodel_facade)

AutoModelCampaignConfig = _db_automodel.AutoModelCampaignConfig
DatabaseTableSource = _db_automodel.DatabaseTableSource
list_automodel_specs = _db_automodel.list_automodel_specs
load_database_table = _db_automodel.load_database_table
prepare_panel = _db_automodel.prepare_panel
run_automodel_campaign = _db_automodel.run_automodel_campaign

__all__ = [
    "AutoModelCampaignConfig",
    "DatabaseTableSource",
    "list_automodel_specs",
    "load_database_table",
    "prepare_panel",
    "run_automodel_campaign",
]
