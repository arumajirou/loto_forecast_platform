from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from loto_ops.config import load_settings
from loto_ops.db.connection import make_engine


@st.cache_resource
def get_engine():
    return make_engine(load_settings().db)


@st.cache_data(ttl=10)
def get_status() -> dict:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT current_database(), current_user, now()::text")).one()
    return {"database": row[0], "user": row[1], "checked_at": row[2]}


@st.cache_data(ttl=30)
def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    return pd.read_sql_query(text(sql), get_engine(), params=params or {})
