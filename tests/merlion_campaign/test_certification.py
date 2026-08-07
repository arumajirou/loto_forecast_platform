from __future__ import annotations

import json
import sys
from pathlib import Path

from loto.merlion_campaign.certification import certify_core_model
from loto.merlion_campaign.protocol import Operation, ProviderRequest, SeriesPayload


FAKE_PROVIDER = r"""
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--request', type=Path, required=True)
parser.add_argument('--response', type=Path, required=True)
parser.add_argument('--work-root', type=Path, required=True)
args = parser.parse_args()
request = json.loads(args.request.read_text())
if request['operation'] == 'train_save':
    evidence = {'model_manifest_sha256': 'a' * 64}
else:
    evidence = {'model_manifest_sha256': request['expected_manifest_sha256']}
response = {
    'schema_version': 'merlion-provider-response-v1',
    'request_id': request['request_id'],
    'status': 'PASS',
    'phase': request['operation'],
    'message': 'ok',
    'process_id': os.getpid(),
    'evidence': evidence,
    'prediction': {
        'timestamps': ['2026-01-01T00:00:00+00:00'],
        'values': [4.0],
        'standard_errors': [0.5],
    },
}
args.response.write_text(json.dumps(response))
"""


def test_certification_requires_distinct_process_and_prediction_match(tmp_path: Path) -> None:
    provider = tmp_path / "fake_provider.py"
    provider.write_text(FAKE_PROVIDER, encoding="utf-8")
    request = ProviderRequest(
        request_id="cert-1",
        operation=Operation.TRAIN_SAVE,
        model_name="Arima",
        series=SeriesPayload(
            name="y",
            values=[1.0, 2.0, 3.0],
            draw_numbers=[1, 2, 3],
        ),
    )
    result = certify_core_model(
        [sys.executable, str(provider)],
        request,
        tmp_path / "work",
    )
    assert result.status == "RUNTIME_VERIFIED"
    assert result.train_process_id != result.load_process_id
    assert result.prediction_match is True
