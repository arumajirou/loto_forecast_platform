"""Formal HierarchicalForecast target-certification constants."""

TARGET_VERSION = "1.5.1"
FORMAL_SEED = 1
FORMAL_HORIZON = 4
FORMAL_INSAMPLE_SIZE = 32
FORMAL_TOLERANCE = 1e-8
GAMES = ("mini", "loto6", "loto7", "bingo5")
EXECUTABLE = (
    "BottomUp",
    "BottomUpSparse",
    "MinTrace",
    "MinTraceSparse",
    "OptimalCombination",
    "ERM",
)
UNSUPPORTED = ("TopDown", "TopDownSparse", "MiddleOut", "MiddleOutSparse")
METHODS = (*EXECUTABLE, *UNSUPPORTED)
EXPECTED_STATUS = {
    **{method: "VERIFIED" for method in EXECUTABLE},
    **{method: "UNSUPPORTED_HIERARCHY" for method in UNSUPPORTED},
}
PRIMARY = (
    "RUNTIME_CERTIFICATION.json",
    "METHOD_RESULTS.json",
    "INPUT_EVIDENCE.json",
    "ARTIFACT_MANIFEST.json",
)
REQUIRED = (*PRIMARY, "SHA256SUMS")
PACKAGE_MANIFEST = "PACKAGE_MANIFEST.json"


class CertificationError(RuntimeError):
    """Raised when target-machine evidence cannot be accepted."""
