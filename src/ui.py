import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import merge_config, validate_config
from main import run_pipeline


st.set_page_config(page_title="AI Budgeting & Forecasting", layout="wide")

st.title("AI Budgeting & Forecasting")
st.caption("Upload data, configure forecasting, and review outputs in one place.")


@st.cache_data
def preview_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(uploaded_file)
    elif suffix in [".xlsx", ".xls"]:
        return pd.read_excel(uploaded_file)
    else:
        raise ValueError("Unsupported file type. Please upload CSV or Excel.")


def save_uploaded_file(uploaded_file) -> str:
    upload_dir = ROOT_DIR / "uploaded_files"
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(file_path)


def read_output_csv(output_dir: str, name: str):
    path = Path(output_dir) / f"{name}.csv"
    if path.exists():
        return pd.read_csv(path)
    return None


with st.sidebar:
    st.header("Setup")

    uploaded_file = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])

    model = st.selectbox(
        "Model",
        ["ensemble", "prophet", "sarima", "lightgbm", "naive"],
        index=0
    )

    periods = st.number_input("Forecast periods", min_value=1, max_value=36, value=6, step=1)
    forecast_grain = st.selectbox("Forecast grain", ["monthly", "weekly", "daily"], index=0)
    aggregation_method = st.selectbox("Aggregation method", ["sum", "mean", "last"], index=0)

    st.subheader("Calibration")
    use_calibration = st.toggle("Use calibration", value=True)
    calibration_window = st.number_input("Calibration window", min_value=3, max_value=24, value=6, step=1)

    st.subheader("Budget Weights")
    budget_seasonal_weight = st.slider("Seasonal weight", 0.0, 1.0, 0.5, 0.1)
    budget_rolling_weight = st.slider("Recent rolling weight", 0.0, 1.0, 0.3, 0.1)
    budget_trend_weight = st.slider("Trend weight", 0.0, 1.0, 0.2, 0.1)
    budget_rolling_window = st.number_input("Budget rolling window", min_value=3, max_value=24, value=6, step=1)

    st.subheader("Rolling Forecast")
    rolling_forecast = st.toggle("Enable rolling forecast", value=False)
    rolling_horizon = st.number_input("Rolling horizon", min_value=1, max_value=12, value=3, step=1)
    min_train = st.number_input("Minimum train periods", min_value=6, max_value=60, value=12, step=1)

    st.subheader("Events")
    events_enabled = st.toggle("Enable events", value=True)
    include_ramzan = st.toggle("Include Ramzan", value=True)
    include_eid = st.toggle("Include Eid", value=True)

    run_label = st.text_input("Run label", value="ui_run")
    output_dir = st.text_input("Output directory", value="output")


if uploaded_file is not None:
    try:
        preview_df = preview_file(uploaded_file)

        st.subheader("Data Preview")
        st.dataframe(preview_df.head(20), use_container_width=True)

        all_columns = list(preview_df.columns)
        numeric_cols = list(preview_df.select_dtypes(include="number").columns)
        non_numeric_cols = [c for c in all_columns if c not in numeric_cols]

        c1, c2 = st.columns(2)
        with c1:
            value_column = st.selectbox("Value column", numeric_cols)
        with c2:
            group_dims = st.multiselect("Group dimensions", non_numeric_cols, default=[])

        if st.button("Run Forecasting Pipeline", type="primary"):
            with st.spinner("Running pipeline... please wait."):
                saved_path = save_uploaded_file(uploaded_file)

                cfg = merge_config({
                    "data_file": saved_path,
                    "value_column": value_column,
                    "group_dims": group_dims,
                    "model": model,
                    "periods": int(periods),
                    "forecast_grain": forecast_grain,
                    "aggregation_method": aggregation_method,
                    "budget_seasonal_weight": float(budget_seasonal_weight),
                    "budget_rolling_weight": float(budget_rolling_weight),
                    "budget_trend_weight": float(budget_trend_weight),
                    "budget_rolling_window": int(budget_rolling_window),
                    "use_calibration": bool(use_calibration),
                    "calibration_window": int(calibration_window),
                    "rolling_forecast": bool(rolling_forecast),
                    "rolling_horizon": int(rolling_horizon),
                    "min_train": int(min_train),
                    "save_learning_history": True,
                    "output_dir": output_dir,
                    "run_label": run_label,
                    "events": {
                        "enabled": events_enabled,
                        "country": "PK",
                        "include_ramzan": include_ramzan,
                        "include_eid": include_eid,
                        "include_black_friday": False,
                        "custom_events": [],
                    },
                })

                validate_config(cfg)
                result = run_pipeline(cfg)

                st.session_state["run_result"] = result
                st.session_state["output_dir"] = output_dir

            st.success("Pipeline run completed.")

        if "output_dir" in st.session_state:
            out_dir = st.session_state["output_dir"]

            st.subheader("Outputs")

            tabs = st.tabs([
                "Forecast",
                "Budget vs Forecast vs Actual",
                "Budget",
                "Variance",
                "Learning",
                "Rolling Forecast"
            ])

            with tabs[0]:
                df = read_output_csv(out_dir, "forecast")
                if df is not None:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("forecast.csv not found.")

            with tabs[1]:
                df = read_output_csv(out_dir, "budget_forecast_actual_monthly")
                if df is None:
                    df = read_output_csv(out_dir, "budget_forecast_actual")
                if df is not None:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("BvFvA output not found.")

            with tabs[2]:
                df = read_output_csv(out_dir, "budget")
                if df is not None:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("budget.csv not found.")

            with tabs[3]:
                df = read_output_csv(out_dir, "variance")
                if df is not None:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("variance.csv not found.")

            with tabs[4]:
                summary = read_output_csv(out_dir, "learning_summary")
                flags = read_output_csv(out_dir, "learning_flags")

                if summary is not None:
                    st.markdown("### Learning Summary")
                    st.dataframe(summary, use_container_width=True)

                if flags is not None:
                    st.markdown("### Learning Flags")
                    st.dataframe(flags, use_container_width=True)

                if summary is None and flags is None:
                    st.info("No learning outputs found.")

            with tabs[5]:
                df = read_output_csv(out_dir, "rolling_forecast")
                if df is not None:
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("rolling_forecast.csv not found.")

    except Exception as e:
        st.error(f"Run failed: {e}")
else:
    st.info("Upload a file to begin.")