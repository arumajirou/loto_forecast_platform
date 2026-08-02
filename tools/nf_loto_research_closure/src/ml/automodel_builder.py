"""
AutoModel の組み立てロジック。

- loss / valid_loss は同じインスタンスを使う
- early_stop_patience_steps によりアーリーストッピング有効/無効を制御
- hist_/stat_/futr_ 接頭辞で外生変数を自動検出
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from neuralforecast.auto import (
    AutoTFT,
    AutoNHITS,
    AutoNBEATS,
    AutoMLP,
    AutoLSTM,
    AutoRNN,
    AutoPatchTST,
    AutoMLPMultivariate,
    AutoTimeMixer,
)
from neuralforecast.core import NeuralForecast
from neuralforecast.losses.pytorch import (
    MAE,
    MSE,
    SMAPE,
)

from .model_registry import get_model_spec


LOSS_NAME_MAP = {
    "mae": MAE,
    "mse": MSE,
    "smape": SMAPE,
}


@dataclass
class ExogenousColumns:
    hist_exog: List[str]
    stat_exog: List[str]
    futr_exog: List[str]


def split_exog_columns(df_columns) -> ExogenousColumns:
    """hist_/stat_/futr_ の接頭辞で列を振り分ける。"""
    hist = [c for c in df_columns if c.startswith("hist_")]
    stat = [c for c in df_columns if c.startswith("stat_")]
    futr = [c for c in df_columns if c.startswith("futr_")]
    return ExogenousColumns(hist_exog=hist, stat_exog=stat, futr_exog=futr)


def get_loss_instance(name: str):
    """文字列指定の loss 名から損失インスタンスを返す。"""
    key = (name or "").lower()
    if key not in LOSS_NAME_MAP:
        raise ValueError(f"未知の loss 名です: {name!r}")
    return LOSS_NAME_MAP[key]()


def _resolve_early_stop_config(early_stop: Optional[bool], patience: int = 3) -> Dict[str, Any]:
    """early_stop_patience_steps を構築。

    - early_stop が True の場合: patience を設定
    - False の場合: -1 (無効)
    - None の場合: ライブラリ既定値に任せる
    """
    if early_stop is True:
        return {"early_stop_patience_steps": int(patience)}
    if early_stop is False:
        return {"early_stop_patience_steps": -1}
    return {}


def build_auto_model(
    model_name: str,
    backend: str,
    h: int,
    loss_name: str,
    num_samples: int,
    search_space: Optional[Dict[str, Any]] = None,
    early_stop: Optional[bool] = None,
    early_stop_patience_steps: int = 3,
    verbose: bool = True,
) -> Any:
    """AutoModel インスタンスを構築する。

    backend: "ray" または "optuna"
    early_stop: True/False/None
    """
    model_name = model_name.strip()
    backend = backend.strip().lower()
    if backend not in {"ray", "optuna"}:
        raise ValueError(f"backend は 'ray' または 'optuna' を指定してください (got={backend!r})")

    loss = get_loss_instance(loss_name)

    early_cfg = _resolve_early_stop_config(early_stop, early_stop_patience_steps)
    common_kwargs: Dict[str, Any] = {
        "h": h,
        "loss": loss,
        "num_samples": num_samples,
        "backend": backend,
        "config": search_space,
        "verbose": verbose,
        "valid_loss": loss,  # 学習/検証とも同じ loss
        **early_cfg,
    }

    # モデル名に応じてクラスを選択
    if model_name == "AutoTFT":
        model = AutoTFT(**common_kwargs)
    elif model_name == "AutoNHITS":
        model = AutoNHITS(**common_kwargs)
    elif model_name == "AutoNBEATS":
        model = AutoNBEATS(**common_kwargs)
    elif model_name == "AutoMLP":
        model = AutoMLP(**common_kwargs)
    elif model_name == "AutoLSTM":
        model = AutoLSTM(**common_kwargs)
    elif model_name == "AutoRNN":
        model = AutoRNN(**common_kwargs)
    elif model_name == "AutoPatchTST":
        model = AutoPatchTST(**common_kwargs)
    elif model_name == "AutoMLPMultivariate":
        model = AutoMLPMultivariate(**common_kwargs)
    elif model_name == "AutoTimeMixer":
        model = AutoTimeMixer(**common_kwargs)
    else:
        raise ValueError(f"未対応の AutoModel: {model_name!r}")

    return model


def build_neuralforecast(
    model,
    freq: str,
    local_scaler_type: Optional[str],
) -> NeuralForecast:
    """NeuralForecast Core を構築する。"""
    kwargs: Dict[str, Any] = {"models": [model], "freq": freq}
    if local_scaler_type:
        kwargs["local_scaler_type"] = local_scaler_type
    nf = NeuralForecast(**kwargs)
    return nf
