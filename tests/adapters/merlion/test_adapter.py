from __future__ import annotations

import sys
from pathlib import Path

import pytest

from loto.adapters.merlion.adapter import MerlionProviderAdapter, MerlionProviderError
from loto.merlion_campaign.protocol import Operation, ProviderRequest

SLEEP_PROVIDER = r"""
import argparse
import time
parser = argparse.ArgumentParser()
parser.add_argument('--request')
parser.add_argument('--response')
parser.add_argument('--work-root')
parser.parse_args()
time.sleep(2)
"""


def test_adapter_enforces_timeout(tmp_path: Path) -> None:
    provider = tmp_path / "sleep_provider.py"
    provider.write_text(SLEEP_PROVIDER, encoding="utf-8")
    adapter = MerlionProviderAdapter(
        [sys.executable, str(provider)],
        timeout_seconds=0.05,
    )
    request = ProviderRequest(request_id="timeout-1", operation=Operation.IDENTITY)
    with pytest.raises(MerlionProviderError, match="timed out"):
        adapter.run(request, tmp_path / "work")
