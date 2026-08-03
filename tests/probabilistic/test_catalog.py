from __future__ import annotations

import hashlib

from loto.probabilistic.catalog import (
    build_unified_catalog_rows,
    catalog_counts,
    list_inference_profiles,
    list_probabilistic_model_specs,
    unified_catalog_counts,
)


def test_catalog_has_all_designed_entries() -> None:
    models = list_probabilistic_model_specs()
    profiles = list_inference_profiles()
    assert len(models) == 75
    assert len(profiles) == 29
    assert len({item.model_id for item in models}) == 75
    assert len({item.profile_id for item in profiles}) == 29
    assert all(item.implementation_status == "IMPLEMENTED" for item in models)


def test_unified_catalog_is_computed_not_hard_coded() -> None:
    counts = unified_catalog_counts()
    assert counts == {"existing": 174, "probabilistic": 75, "total": 249}
    rows = build_unified_catalog_rows()
    assert len({row["model_id"] for row in rows}) == len(rows)
    assert catalog_counts()["probabilistic_models"] == 75


def test_ppl01_model_ids_remain_byte_for_byte_stable() -> None:
    model_ids = [item.model_id for item in list_probabilistic_model_specs()]
    ppl02_ids = {
        "pp-conditional-bernoulli-fixed-k",
        "pp-multinomial-dglm",
        "pp-gaussian-copula-categorical",
    }
    ppl01_ids = [item for item in model_ids if item not in ppl02_ids]
    ordered = ("\n".join(ppl01_ids) + "\n").encode()
    sorted_ids = ("\n".join(sorted(ppl01_ids)) + "\n").encode()
    assert len(ppl01_ids) == 72
    assert hashlib.sha256(ordered).hexdigest() == (
        "cc6f1a0a5ac68d3b08f07ea410cda4418e69a541c2527d73cf5bd199d8f95273"
    )
    assert hashlib.sha256(sorted_ids).hexdigest() == (
        "5f38b64fcf4d2edf193ea942d8bccb115369d928a7626f58fb4128cd3aa1a80a"
    )
