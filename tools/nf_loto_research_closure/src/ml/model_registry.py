"""
NeuralForecast AutoModel のレジストリ。
モデルごとの外生変数サポート (F/H/S) をここで定義しておき、
UI からの選択や自動検証で利用できるようにする。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Type

# AutoModel は実行環境側で import される想定 (ここでは型名のみ文字列管理でもよい)
# from neuralforecast.auto import AutoTFT, AutoNHITS, AutoNBEATS, AutoMLP, AutoLSTM, AutoRNN, AutoKAN, AutoMLPMultivariate, AutoPatchTST, AutoTimeMixer ...


@dataclass(frozen=True)
class ExogenousSupport:
    futr: bool  # F: futr_exog_list
    hist: bool  # H: hist_exog_list
    stat: bool  # S: stat_exog_list


@dataclass(frozen=True)
class AutoModelSpec:
    name: str                # "AutoTFT" など
    family: str              # "Transformer" / "MLP" / ...
    univariate: bool
    multivariate: bool
    forecast_type: str       # "direct" / "recursive" / "both"
    exogenous: ExogenousSupport


# 必要に応じて拡張可能なレジストリ
AUTO_MODEL_REGISTRY: Dict[str, AutoModelSpec] = {
    "AutoTFT": AutoModelSpec(
        name="AutoTFT",
        family="Transformer",
        univariate=True,
        multivariate=False,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoNHITS": AutoModelSpec(
        name="AutoNHITS",
        family="MLP",
        univariate=True,
        multivariate=False,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoNBEATS": AutoModelSpec(
        name="AutoNBEATS",
        family="MLP",
        univariate=True,
        multivariate=False,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=False, hist=False, stat=False),
    ),
    "AutoMLP": AutoModelSpec(
        name="AutoMLP",
        family="MLP",
        univariate=True,
        multivariate=False,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoLSTM": AutoModelSpec(
        name="AutoLSTM",
        family="RNN",
        univariate=True,
        multivariate=False,
        forecast_type="both",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoRNN": AutoModelSpec(
        name="AutoRNN",
        family="RNN",
        univariate=True,
        multivariate=False,
        forecast_type="both",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoPatchTST": AutoModelSpec(
        name="AutoPatchTST",
        family="Transformer",
        univariate=True,
        multivariate=False,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=False, hist=False, stat=False),
    ),
    "AutoMLPMultivariate": AutoModelSpec(
        name="AutoMLPMultivariate",
        family="MLP",
        univariate=False,
        multivariate=True,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=True, hist=True, stat=True),
    ),
    "AutoTimeMixer": AutoModelSpec(
        name="AutoTimeMixer",
        family="MLP",
        univariate=False,
        multivariate=True,
        forecast_type="direct",
        exogenous=ExogenousSupport(futr=False, hist=False, stat=False),
    ),
}


def list_automodel_names() -> List[str]:
    """UI 用のモデル名一覧。"""
    return sorted(AUTO_MODEL_REGISTRY.keys())


def get_model_spec(model_name: str) -> Optional[AutoModelSpec]:
    return AUTO_MODEL_REGISTRY.get(model_name)
