from __future__ import annotations

import importlib.util

import pytest

from loto.basicts_campaign.protocol import ProviderOperation, ProviderRequest, ProviderStatus
from loto.basicts_campaign.runtime import execute_request


@pytest.mark.skipif(importlib.util.find_spec("basicts") is None, reason="BasicTS is unavailable")
def test_real_dlinear_smoke(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "BASICTS_UPSTREAM_REVISION",
        "c2bb6e31e591167e84459775a21a62e70a5893ce",
    )
    request = ProviderRequest(
        operation=ProviderOperation.DLINEAR_SMOKE,
        output_dir=str(tmp_path),
    )
    response = execute_request(request)
    assert response.status is ProviderStatus.PASS
