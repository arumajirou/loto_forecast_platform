import pytest
from pydantic import ValidationError

from loto.config import PlatformConfig, resolve_config


def test_unknown_config_keys_are_rejected():
    with pytest.raises(ValidationError):
        PlatformConfig.model_validate({"runtime": {"production_os": "linux"}, "unknown": 1})


def test_resolved_config_has_deterministic_hash():
    a = resolve_config({"runtime": {"production_os": "linux"}})
    b = resolve_config({"runtime": {"production_os": "linux"}})
    assert a["sha256"] == b["sha256"]
