from __future__ import annotations

import streamlit as st

from loto_ops.webapp.layout import setup_page
from loto_ops.webapp.pages import (
    artifacts,
    data_browser,
    overview,
    pipeline_run,
    quality,
    scheduler,
    settings,
)

PAGES = {
    "Overview": overview.render,
    "Pipeline Run": pipeline_run.render,
    "Data Browser": data_browser.render,
    "Quality": quality.render,
    "Artifacts": artifacts.render,
    "Scheduler": scheduler.render,
    "Settings": settings.render,
}


def main() -> None:
    setup_page()
    st.sidebar.title("Loto Ops Console")
    page = st.sidebar.radio("Page", list(PAGES.keys()))
    PAGES[page]()


if __name__ == "__main__":
    main()
