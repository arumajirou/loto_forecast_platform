from loto.models.implementation_catalog import skforecast_implementation_identities


def test_tabicl_inventory_points_to_verified_checkpoint_artifact() -> None:
    rows = {row.implementation_id: row for row in skforecast_implementation_identities()}
    tabicl = rows["skforecast-foundation-tabicl-v2"]

    assert tabicl.source_alias == "soda-inria/tabicl"
    assert tabicl.artifact_id == "jingang/TabICL/tabicl-regressor-v2-20260212.ckpt"
    assert tabicl.artifact_revision == "4dcd344ece2c00be9e831fdd35bed57b5ad83e19"
    assert (
        tabicl.artifact_sha256
        == "0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a"
    )


def test_unexecuted_t0_exogenous_support_is_source_declared_not_runtime_capability() -> None:
    rows = {row.implementation_id: row for row in skforecast_implementation_identities()}
    t0 = rows["skforecast-foundation-t0"]

    assert t0.runtime_status == "NOT_RUN"
    assert "exogenous" not in t0.capabilities
    assert "exogenous_source_declared" in t0.capabilities
    assert t0.runtime_certified is False


def test_tabpfn_exogenous_contract_is_not_inference_certification() -> None:
    rows = {row.implementation_id: row for row in skforecast_implementation_identities()}
    tabpfn = rows["skforecast-foundation-tabpfn-ts3"]

    assert "exogenous" not in tabpfn.capabilities
    assert "exogenous_contract_verified" in tabpfn.capabilities
    assert tabpfn.runtime_status == "BLOCKED_INVALID_OR_EXPIRED_TOKEN"
    assert tabpfn.runtime_certified is False
