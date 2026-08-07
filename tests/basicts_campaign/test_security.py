from __future__ import annotations

import pytest

from loto.basicts_campaign.contracts import ImportReference, SafeConfig
from loto.basicts_campaign.security import UnsafeImportReference, validate_safe_config


def test_allowlisted_references_pass_without_import() -> None:
    resolved = validate_safe_config(SafeConfig(), resolve=False)
    assert resolved["model"].endswith("TinyLinearForecaster")
    assert resolved["optimizer"] == "torch.optim.Adam"


def test_non_allowlisted_module_fails_closed() -> None:
    config = SafeConfig(model=ImportReference(module="os", name="system"))
    with pytest.raises(UnsafeImportReference, match="not allowlisted"):
        validate_safe_config(config)


def test_private_object_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        ImportReference(module="torch.optim", name="__dict__")
