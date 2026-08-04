from __future__ import annotations

from .contracts import CampaignConfig

HEAVY_MODELS = {
    "AutoHINT",
    "AutoPatchTST",
    "AutoTFT",
    "AutoAutoformer",
    "AutoFEDformer",
    "AutoInformer",
    "AutoVanillaTransformer",
    "AutoiTransformer",
    "AutoTimeXer",
    "AutoTimesNet",
    "AutoStemGNN",
    "AutoSOFTS",
    "AutoSOFTSSharp",
    "AutoTimeMixer",
    "AutoRMoK",
}

MEDIUM_MODELS = {
    "AutoDeepAR",
    "AutoDilatedRNN",
    "AutoBiTCN",
    "AutoxLSTM",
    "AutoNBEATS",
    "AutoNBEATSx",
    "AutoNHITS",
    "AutoTiDE",
    "AutoTSMixer",
    "AutoTSMixerx",
    "AutoMLPMultivariate",
    "AutoXLinear",
}


def resource_profile_name(model_name: str) -> str:
    if model_name in HEAVY_MODELS:
        return "heavy"
    if model_name in MEDIUM_MODELS:
        return "medium"
    return "light"


def apply_model_resource_profile(
    config: CampaignConfig,
    model_name: str,
) -> CampaignConfig:
    if config.resources.accelerator != "gpu":
        return config
    profile = resource_profile_name(model_name)
    if profile == "heavy":
        gpu_fraction, concurrency = 1.0, 1
    elif profile == "medium":
        gpu_fraction, concurrency = 0.5, 2
    else:
        gpu_fraction, concurrency = 0.25, 4
    resources = config.resources.model_copy(
        update={
            "gpus_per_trial": gpu_fraction,
            "gpu_concurrency": concurrency,
        }
    )
    return config.model_copy(update={"resources": resources})
