from pathlib import Path

import pytest
from pydantic import ValidationError

from loto.experiment_config import ExperimentConfig


def test_research_config_is_valid():
    cfg = ExperimentConfig.from_file(Path("configs/research_full.yaml"))
    assert cfg.schema_version == "2.1.0"
    assert cfg.config_hash
    assert "nf-nhits" in cfg.models


def test_unknown_config_key_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("data: {input: x.csv}\nruntime: {output: runs/x}\nunknown: 1\n")
    with pytest.raises(ValidationError):
        ExperimentConfig.from_file(path)
