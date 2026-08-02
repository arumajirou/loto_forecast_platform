"""
nf_loto テーブルからデータを取得し、NeuralForecast AutoModel を実行する高水準 API。

- run_loto_experiment: 単一設定で 1 本の実験を実行
- sweep_loto_experiments: パラメータグリッドで網羅的に実行

loto × unique_ids × AutoModel × backend × search_space × loss × h × refit_with_val ×
freq × local_scaler_type × val_size × use_init_models × early_stop
の組み合わせを制御できるようにしている。
"""

from __future__ import annotations

import json
import os
import platform
import socket
import time
from dataclasses import dataclass, asdict
from itertools import product
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from neuralforecast.core import NeuralForecast

from src.data_access.loto_repository import load_panel_by_loto
from src.logging.db_logger import log_run_start, log_run_end, log_run_error
from src.monitoring.resource_monitor import collect_resource_snapshot
from src.monitoring.prometheus_metrics import (
    init_metrics_server,
    observe_run_start,
    observe_run_end,
    observe_run_error,
)
from .automodel_builder import (
    build_auto_model,
    build_neuralforecast,
    split_exog_columns,
)


@dataclass
class LotoExperimentResult:
    run_id: int
    preds: pd.DataFrame
    meta: Dict[str, Any]


DEFAULT_SWEEP_PARAMS: Dict[str, Any] = {
    "loss": ["mse"],
    "h": [28],
    "refit_with_val": [True],
    "freq": ["D"],
    "local_scaler_type": ["robust"],
    "val_size": ["2h"],
    "use_init_models": [False],
    "early_stop": [True],
}


def _system_info() -> Dict[str, Any]:
    return {
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "pid": os.getpid(),
    }


def _build_param_grid(
    user_spec: Optional[Dict[str, Any]] = None,
    mode: str = "defaults",
) -> List[Dict[str, Any]]:
    """ユーザ指定 + デフォルトからパラメータグリッドを構築。

    mode:
        - "defaults": 各パラメータ 1 値のみで 1 通りだけ実行
        - "grid":     リスト指定パラメータの Cartesian product を取る
    """
    base = dict(DEFAULT_SWEEP_PARAMS)
    if user_spec:
        base.update(user_spec)

    if mode == "defaults":
        single = {}
        for k, v in base.items():
            if isinstance(v, (list, tuple, set)):
                v = list(v)[0]
            single[k] = v
        return [single]

    # grid モード
    keys = list(base.keys())
    values_lists: List[List[Any]] = []
    for k in keys:
        v = base[k]
        if isinstance(v, (list, tuple, set)):
            values_lists.append(list(v))
        else:
            values_lists.append([v])

    combos: List[Dict[str, Any]] = []
    for values in product(*values_lists):
        combos.append(dict(zip(keys, values)))
    return combos


def _prepare_dataset(panel_df: pd.DataFrame):
    """NeuralForecast 用の df, 外生変数リストを準備。"""
    exogs = split_exog_columns(panel_df.columns)
    # TimeSeriesDataset を使わず、NeuralForecast に df をそのまま渡す想定
    futr_exog_list = exogs.futr_exog or None
    hist_exog_list = exogs.hist_exog or None
    stat_exog_list = exogs.stat_exog or None
    return panel_df, futr_exog_list, hist_exog_list, stat_exog_list


def run_loto_experiment(
    table_name: str,
    loto: str,
    unique_ids: Sequence[str],
    model_name: str,
    backend: str,
    horizon: int,
    loss: str,
    metric: str,
    num_samples: int,
    cpus: int = 1,
    gpus: int = 0,
    search_space: Optional[Dict[str, Any]] = None,
    freq: str = "D",
    local_scaler_type: Optional[str] = "robust",
    val_size: Optional[int] = None,
    refit_with_val: bool = True,
    use_init_models: bool = False,
    early_stop: Optional[bool] = True,
    early_stop_patience_steps: int = 3,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """単一設定で AutoModel 実験を 1 回実行し、予測結果とメタ情報を返す。

    verbose=True / loss==valid_loss は automodel_builder 側で設定。
    """
    start_ts = time.time()
    # Prometheus metrics サーバを必要に応じて起動 (複数回呼ばれても安全)
    try:
        init_metrics_server(port=int(os.getenv("NF_METRICS_PORT", "8000")))
    except Exception:  # noqa: BLE001
        # 監視系の初期化失敗で実験本体が落ちないようにする
        pass

    start_resources = collect_resource_snapshot()
    system_info = _system_info()

    optimization_config = {
        "backend": backend,
        "num_samples": num_samples,
        "cpus": cpus,
        "gpus": gpus,
        "val_size": val_size,
        "refit_with_val": refit_with_val,
        "use_init_models": use_init_models,
        "early_stop": early_stop,
        "early_stop_patience_steps": early_stop_patience_steps,
    }

    run_id = log_run_start(
        table_name=table_name,
        loto=loto,
        unique_ids=unique_ids,
        model_name=model_name,
        backend=backend,
        horizon=horizon,
        loss=loss,
        metric=metric,
        optimization_config=optimization_config,
        search_space=search_space or {},
        resource_snapshot=start_resources,
        system_info=system_info,
    )

    # Prometheus: 実行開始を通知
    observe_run_start(model_name=model_name, backend=backend)

    try:
        panel_df = load_panel_by_loto(table_name=table_name, loto=loto, unique_ids=unique_ids)
        df, futr_exog_list, hist_exog_list, stat_exog_list = _prepare_dataset(panel_df)

        model = build_auto_model(
            model_name=model_name,
            backend=backend,
            h=horizon,
            loss_name=loss,
            num_samples=num_samples,
            search_space=search_space,
            early_stop=early_stop,
            early_stop_patience_steps=early_stop_patience_steps,
            verbose=True,
        )

        nf = build_neuralforecast(
            model=model,
            freq=freq,
            local_scaler_type=local_scaler_type,
        )

        # fit
        nf.fit(
            df=df,
            futr_exog_list=futr_exog_list,
            hist_exog_list=hist_exog_list,
            stat_exog_list=stat_exog_list,
            verbose=True,
        )

        # cross_validation や refit_with_val などは、必要に応じて別ラッパー関数で扱う想定
        preds = nf.predict()

        # モデル保存 (パスは実行環境側で適宜変更)
        model_dir = os.path.join("artifacts", f"run_{run_id}")
        os.makedirs(model_dir, exist_ok=True)
        nf.save(path=model_dir)

        after_resources = collect_resource_snapshot()

        meta = {
            "run_id": run_id,
            "table_name": table_name,
            "loto": loto,
            "unique_ids": list(unique_ids),
            "model_name": model_name,
            "backend": backend,
            "horizon": horizon,
            "loss": loss,
            "metric": metric,
            "num_samples": num_samples,
            "freq": freq,
            "local_scaler_type": local_scaler_type,
            "val_size": val_size,
            "refit_with_val": refit_with_val,
            "use_init_models": use_init_models,
            "early_stop": early_stop,
            "early_stop_patience_steps": early_stop_patience_steps,
            "model_dir": model_dir,
        }

        # 今回は metrics の詳細は埋めない (必要なら cross_validation の結果などを集計して入れる)
        log_run_end(
            run_id=run_id,
            status="finished",
            metrics={},
            best_params={},  # AutoModel 側から取得する場合はここに格納
            model_properties={},
            resource_after=after_resources,
            extra_logs="",
        )

        # Prometheus: 正常終了を通知
        duration = time.time() - start_ts
        observe_run_end(
            model_name=model_name,
            backend=backend,
            status="finished",
            duration_seconds=duration,
            resource_after=after_resources,
        )

        return preds, meta

    except Exception as exc:  # noqa: BLE001 - ログ用に広く捕捉
        log_run_error(run_id, exc)
        try:
            duration = time.time() - start_ts
            observe_run_end(
                model_name=model_name,
                backend=backend,
                status="failed",
                duration_seconds=duration,
                resource_after=None,
            )
            observe_run_error(model_name=model_name, backend=backend)
        except Exception:  # noqa: BLE001
            # 監視系で例外が出ても学習の例外を上書きしない
            pass
        raise


def sweep_loto_experiments(
    table_name: str,
    loto: str,
    unique_ids: Sequence[str],
    model_names: Sequence[str],
    backends: Sequence[str],
    param_spec: Optional[Dict[str, Any]] = None,
    mode: str = "defaults",
    num_samples: int = 10,
    cpus: int = 1,
    gpus: int = 0,
) -> List[LotoExperimentResult]:
    """loto × unique_ids × AutoModel × backend × ... の組み合わせを一括実行。

    param_spec には loss/h/freq/local_scaler_type/val_size/refit_with_val/use_init_models/early_stop 等を
    単一値またはリストで指定可能。

    mode:
        - "defaults": デフォルト + 単一値で 1 組のみ
        - "grid":     リストを Cartesian product で全探索
    """
    grid = _build_param_grid(user_spec=param_spec, mode=mode)

    results: List[LotoExperimentResult] = []

    for model_name in model_names:
        for backend in backends:
            for params in grid:
                preds, meta = run_loto_experiment(
                    table_name=table_name,
                    loto=loto,
                    unique_ids=unique_ids,
                    model_name=model_name,
                    backend=backend,
                    horizon=int(params["h"]),
                    loss=str(params["loss"]),
                    metric="val_loss",
                    num_samples=num_samples,
                    cpus=cpus,
                    gpus=gpus,
                    search_space=param_spec.get("search_space") if param_spec else None,
                    freq=str(params.get("freq", "D")),
                    local_scaler_type=params.get("local_scaler_type", "robust"),
                    val_size=params.get("val_size"),
                    refit_with_val=bool(params.get("refit_with_val", True)),
                    use_init_models=bool(params.get("use_init_models", False)),
                    early_stop=params.get("early_stop"),
                    early_stop_patience_steps=int(
                        params.get("early_stop_patience_steps", 3)
                    ),
                )
                results.append(LotoExperimentResult(run_id=meta["run_id"], preds=preds, meta=meta))

    return results
