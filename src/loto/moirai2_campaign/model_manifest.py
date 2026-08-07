from __future__ import annotations

MODEL_ID = "moirai-2.0-r-small"
REPO_ID = "Salesforce/moirai-2.0-R-small"
MODEL_REVISION = "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
SOURCE_REVISION = "cfd46d4510ed8896f263116f32928eede05b0a75"
UNI2TS_VERSION = "2.0.0"
UNI2TS_WHEEL_SHA256 = "7bb185392885e3f0cb53773a5fb0b922d99bf56e93790332d23abb3a4fa01612"
UNI2TS_SDIST_SHA256 = "184b386db71a92f94a8961c1010fbcc126814b873faabc6a76ed680579c8d4be"
MODEL_WEIGHT_SHA256 = "fb5652a3db8ea572606221b7cb1e77bb8962b168e4d4cc752cf31ceb04074669"
MODEL_CONFIG_SHA256 = "6b74b03c8ec199fabc352c0203465958142ca468183da68549652734836f853d"
PATCH_SIZE = 16
MAX_SEQUENCE_TOKENS = 512
NUM_PREDICT_TOKENS = 4
NATIVE_QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
FORMAL_HORIZONS = (1, 2, 5)

MODEL_MANIFEST = {
    "model_id": MODEL_ID,
    "repo_id": REPO_ID,
    "model_revision": MODEL_REVISION,
    "source_revision": SOURCE_REVISION,
    "package": "uni2ts",
    "package_version": UNI2TS_VERSION,
    "package_wheel_sha256": UNI2TS_WHEEL_SHA256,
    "package_sdist_sha256": UNI2TS_SDIST_SHA256,
    "model_weight_sha256": MODEL_WEIGHT_SHA256,
    "model_config_sha256": MODEL_CONFIG_SHA256,
    "model_license": "CC-BY-NC-4.0",
    "code_license": "Apache-2.0",
    "patch_size": PATCH_SIZE,
    "max_sequence_tokens": MAX_SEQUENCE_TOKENS,
    "num_predict_tokens": NUM_PREDICT_TOKENS,
    "native_quantile_levels": list(NATIVE_QUANTILE_LEVELS),
    "formal_horizons": list(FORMAL_HORIZONS),
}
