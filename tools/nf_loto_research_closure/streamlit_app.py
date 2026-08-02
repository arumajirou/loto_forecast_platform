"""
nf_loto_webui Streamlit アプリ。

- 左ペイン: DB 接続情報表示 (config/db_config.py)
- メイン:
    - タブ1: 実験実行 (単発 + グリッドサーチ)
    - タブ2: 実行履歴ブラウザ (nf_model_runs)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import psycopg2
import streamlit as st

from config.db_config import DB_CONFIG
from src.data_access.loto_repository import (
    list_loto_tables,
    list_loto_values,
    list_unique_ids,
)
from src.ml.model_registry import list_automodel_names
from src.ml.model_runner import run_loto_experiment, sweep_loto_experiments


def _get_connection():
    return psycopg2.connect(**DB_CONFIG)


st.set_page_config(page_title="nf_loto_webui", layout="wide")

st.sidebar.title("nf_loto_webui")
st.sidebar.write("PostgreSQL 上の nf_loto% テーブルから NeuralForecast AutoModel を回すための WebUI。")

st.sidebar.subheader("DB 接続情報")
st.sidebar.json(DB_CONFIG)

tab_run, tab_history = st.tabs(["🧪 実験実行", "📈 実行履歴"])


with tab_run:
    st.header("ロト実験の実行")

    # テーブル / loto / unique_id を DB から選択
    tables_df = list_loto_tables()
    table_name = st.selectbox("対象テーブル (nf_loto%)", tables_df["tablename"].tolist())

    loto_df = list_loto_values(table_name)
    loto = st.selectbox("loto", loto_df["loto"].tolist())

    uid_df = list_unique_ids(table_name, loto)
    all_uids = uid_df["unique_id"].tolist()
    unique_ids = st.multiselect("unique_ids", options=all_uids, default=all_uids[:3])

    st.subheader("モデル / backend / 探索モード")

    model_names = st.multiselect("AutoModel", options=list_automodel_names(), default=["AutoTFT"])
    backends = st.multiselect("backend", options=["ray", "optuna"], default=["optuna"])

    mode = st.radio(
        "パラメータ探索モード",
        options=["defaults", "grid"],
        index=0,
        help="defaults: デフォルトパラメータのみ 1 通り実行 / grid: リストを Cartesian product で全探索",
        horizontal=True,
    )

    st.markdown("### 共通設定")

    num_samples = st.number_input("num_samples (backend のサンプル数)", min_value=1, max_value=1000, value=10, step=1)
    cpus = st.number_input("cpus", min_value=1, max_value=64, value=1)
    gpus = st.number_input("gpus", min_value=0, max_value=8, value=0)
    early_stop = st.checkbox("アーリーストッピングを有効にする", value=True)
    early_stop_patience = st.number_input("early_stop_patience_steps", min_value=-1, max_value=1000, value=3)

    param_spec: Dict[str, Any] = {}

    if mode == "defaults":
        # loto × unique_ids × AutoModel × backend だけ UI で選び、他はデフォルトに任せる
        st.info("defaults モード: loss/h/freq/local_scaler_type/val_size などはデフォルト値で 1 通りのみ実行します。")
        param_spec["early_stop"] = early_stop
        param_spec["early_stop_patience_steps"] = early_stop_patience
    else:
        st.markdown("### グリッド検索パラメータ (カンマ区切りで複数指定)")

        loss_str = st.text_input("loss 候補 (例: mse,mae,smape)", value="mse")
        h_str = st.text_input("horizon 候補 (例: 28,56)", value="28")
        freq_str = st.text_input("freq 候補 (例: D,W,M)", value="D")
        local_scaler_str = st.text_input("local_scaler_type 候補 (例: robust,standard)", value="robust")
        val_size_str = st.text_input("val_size 候補 (例: 28,56)", value="28")
        refit_str = st.text_input("refit_with_val 候補 (例: true,false)", value="true")
        use_init_str = st.text_input("use_init_models 候補 (例: false,true)", value="false")

        def parse_list(s: str, cast=str):
            vals = [x.strip() for x in s.split(",") if x.strip()]
            return [cast(x) for x in vals]

        param_spec = {
            "loss": parse_list(loss_str, str),
            "h": parse_list(h_str, int),
            "freq": parse_list(freq_str, str),
            "local_scaler_type": parse_list(local_scaler_str, str),
            "val_size": parse_list(val_size_str, int),
            "refit_with_val": [v.lower() == "true" for v in parse_list(refit_str, str)],
            "use_init_models": [v.lower() == "true" for v in parse_list(use_init_str, str)],
            "early_stop": [early_stop],
            "early_stop_patience_steps": [early_stop_patience],
        }

    if st.button("実験を実行", type="primary"):
        if not unique_ids:
            st.error("少なくとも 1 つ unique_id を選択してください。")
        elif not model_names:
            st.error("少なくとも 1 つ AutoModel を選択してください。")
        elif not backends:
            st.error("少なくとも 1 つ backend を選択してください。")
        else:
            with st.spinner("実験を実行中..."):
                try:
                    if mode == "defaults":
                        # 1 本だけ実行
                        preds, meta = run_loto_experiment(
                            table_name=table_name,
                            loto=loto,
                            unique_ids=unique_ids,
                            model_name=model_names[0],
                            backend=backends[0],
                            horizon=28,
                            loss="mse",
                            metric="val_loss",
                            num_samples=num_samples,
                            cpus=cpus,
                            gpus=gpus,
                            search_space=None,
                            freq="D",
                            local_scaler_type="robust",
                            val_size=28,
                            refit_with_val=True,
                            use_init_models=False,
                            early_stop=early_stop,
                            early_stop_patience_steps=early_stop_patience,
                        )
                        st.success(f"run_id={meta['run_id']} で実行完了")
                        st.dataframe(preds.head())
                        st.json(meta)
                    else:
                        results = sweep_loto_experiments(
                            table_name=table_name,
                            loto=loto,
                            unique_ids=unique_ids,
                            model_names=model_names,
                            backends=backends,
                            param_spec=param_spec,
                            mode="grid",
                            num_samples=num_samples,
                            cpus=cpus,
                            gpus=gpus,
                        )
                        st.success(f"{len(results)} 本の実験を実行しました。")
                        if results:
                            st.dataframe(results[0].preds.head())
                            st.json(results[0].meta)
                except Exception as exc:
                    st.exception(exc)


with tab_history:
    st.header("実行履歴 (nf_model_runs)")
    try:
        with _get_connection() as conn:
            df_hist = pd.read_sql("SELECT * FROM nf_model_runs ORDER BY id DESC LIMIT 500", conn)
        st.dataframe(df_hist)
    except Exception as exc:
        st.warning("nf_model_runs を取得できませんでした。SQL を実行する前にテーブルを作成してください。")
        st.exception(exc)
