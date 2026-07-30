from loto.sealing.manifest import seal_payload, verify_seal


def test_sealed_payload_detects_tampering():
    sealed = seal_payload({"forecast_id": "fc-1", "numbers": [1, 4, 9, 15, 22, 30, 37]}, secret=b"secret")
    assert verify_seal(sealed, secret=b"secret")
    sealed["payload"]["numbers"][0] = 2
    assert not verify_seal(sealed, secret=b"secret")
