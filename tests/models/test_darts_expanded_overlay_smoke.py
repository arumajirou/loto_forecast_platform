from loto.models.darts_source_inventory import DARTS_SOURCE_EXCLUSIONS
from loto.models.expanded_inventory_v2 import (
    darts_implementation_identities,
    expanded_implementation_catalog,
    expanded_inventory_counts,
)


def test_darts_expanded_overlay_contract() -> None:
    darts = darts_implementation_identities()
    expanded = expanded_implementation_catalog()
    counts = expanded_inventory_counts()

    assert len(darts) == 55
    assert len(DARTS_SOURCE_EXCLUSIONS) == 3
    assert counts["darts_public_exports"] == 58
    assert counts["darts_expanded_total"] == 55
    assert counts["base_expanded_v2"] == 244
    assert counts["expanded_v2"] == len(expanded) == 298
    assert counts["delta_vs_broad_v1"] == 124
    assert counts["by_library"]["darts"] == 55
    assert counts["by_library"]["skforecast"] == 27
    assert all(row.runtime_status == "NOT_RUN" for row in darts)
    assert not any(row.runtime_certified for row in darts)
    assert all(row.capabilities == ("source_declared",) for row in darts)
    assert len({row.implementation_id for row in expanded}) == 298
