import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_service import run_forecasting_app


st.set_page_config(page_title="AI Budgeting & Forecasting", layout="wide")

st.title("AI Budgeting & Forecasting")
st.caption("Upload your file, select the business metric, and generate forecast and budget outputs.")


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


def parse_custom_events(events_text: str) -> list[dict]:
    events = []
    lines = [line.strip() for line in events_text.splitlines() if line.strip()]
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 2:
            name, start_date = parts
            events.append({
                "name": name,
                "start_date": start_date,
                "end_date": start_date,
            })
        elif len(parts) == 3:
            name, start_date, end_date = parts
            events.append({
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            })
    return events


def safe_mean(df: pd.DataFrame | None, col: str):
    if df is None or col not in df.columns or len(df) == 0:
        return None
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(vals) == 0:
        return None
    return float(vals.mean())


def safe_latest(df: pd.DataFrame | None, col: str):
    if df is None or col not in df.columns or len(df) == 0:
        return None
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(vals) == 0:
        return None
    return float(vals.iloc[-1])


def get_learning_message(flags_df: pd.DataFrame | None) -> list[str]:
    msgs = []
    if flags_df is None or len(flags_df) == 0:
        return msgs

    if "forecast_bias_flag" in flags_df.columns:
        flag = str(flags_df["forecast_bias_flag"].iloc[0])
        if flag == "UNDER_FORECASTING":
            msgs.append("Forecast is historically under-estimating actuals.")
        elif flag == "OVER_FORECASTING":
            msgs.append("Forecast is historically over-estimating actuals.")
        elif flag == "BALANCED":
            msgs.append("Forecast bias looks balanced.")

    if "budget_bias_flag" in flags_df.columns:
        flag = str(flags_df["budget_bias_flag"].iloc[0])
        if flag == "UNDER_BUDGETING":
            msgs.append("Budget is historically below actual performance.")
        elif flag == "OVER_BUDGETING":
            msgs.append("Budget is historically above actual performance.")
        elif flag == "BALANCED":
            msgs.append("Budget bias looks balanced.")

    return msgs


with st.sidebar:
    st.header("Setup")

    uploaded_file = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx", "xls"])

    forecast_period = st.selectbox("Forecast Horizon", [3, 6, 12], index=1)

    breakdown_level = st.selectbox(
        "Breakdown Level",
        ["Total Business", "By Location", "By Location & Category"],
        index=0,
    )

    st.subheader("Events")
    include_ramzan = st.checkbox("Include Ramzan", value=True)
    include_eid = st.checkbox("Include Eid", value=True)

    custom_events_text = st.text_area(
        "Custom Events (optional)",
        placeholder="Format:\nSummer Campaign | 2026-06-01 | 2026-06-10\nMega Sale | 2026-11-20",
        height=120,
    )


if uploaded_file is not None:
    try:
        preview_df = preview_file(uploaded_file)

        st.subheader("Data Preview")
        st.dataframe(preview_df.head(20), use_container_width=True)

        numeric_cols = list(preview_df.select_dtypes(include="number").columns)

        if not numeric_cols:
            st.error("No numeric columns found in uploaded file.")
        else:
            value_column = st.selectbox("Business Metric", numeric_cols)

            if st.button("Run Forecast", type="primary"):
                with st.spinner("Running forecasting pipeline... please wait."):
                    saved_path = save_uploaded_file(uploaded_file)
                    custom_events = parse_custom_events(custom_events_text)

                    result = run_forecasting_app(
                        data_file=saved_path,
                        value_column=value_column,
                        periods=int(forecast_period),
                        breakdown_level=breakdown_level,
                        include_ramzan=include_ramzan,
                        include_eid=include_eid,
                        custom_events=custom_events,
                        forecast_grain="monthly",
                        base_output_dir="output",
                    )

                    st.session_state["run_result"] = result
                    st.session_state["output_dir"] = result["output_dir"]
                    st.session_state["run_label"] = result["run_label"]

                st.success("Forecasting pipeline completed successfully.")

        if "output_dir" in st.session_state:
            out_dir = st.session_state["output_dir"]
            run_label = st.session_state.get("run_label", "")

            forecast_df = read_output_csv(out_dir, "forecast")
            learning_summary_df = read_output_csv(out_dir, "learning_summary")
            learning_flags_df = read_output_csv(out_dir, "learning_flags")
            bfa_df = read_output_csv(out_dir, "budget_forecast_actual_monthly")
            if bfa_df is None:
                bfa_df = read_output_csv(out_dir, "budget_forecast_actual")
            variance_df = read_output_csv(out_dir, "variance")
            budget_df = read_output_csv(out_dir, "budget")
            scenarios_df = read_output_csv(out_dir, "scenarios")
            rolling_df = read_output_csv(out_dir, "rolling_forecast")

            st.subheader("Run Summary")
            st.info(f"Run Label: {run_label}")

            # KPI cards
            forecast_mae = safe_mean(learning_summary_df, "forecast_mae")
            forecast_bias = safe_mean(learning_summary_df, "forecast_bias_pct")
            latest_budget = safe_latest(budget_df, "budget")
            latest_forecast = safe_latest(forecast_df, "yhat")

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                st.metric("Forecast MAE", f"{forecast_mae:,.0f}" if forecast_mae is not None else "N/A")

            with c2:
                st.metric("Forecast Bias %", f"{forecast_bias:.1f}%" if forecast_bias is not None else "N/A")

            with c3:
                st.metric("Latest Forecast", f"{latest_forecast:,.0f}" if latest_forecast is not None else "N/A")

            with c4:
                st.metric("Latest Budget", f"{latest_budget:,.0f}" if latest_budget is not None else "N/A")

            # Insights
            st.subheader("Insights")
            msgs = get_learning_message(learning_flags_df)
            if msgs:
                for msg in msgs:
                    st.warning(msg)
            else:
                st.info("No learning insights available yet.")

            tabs = st.tabs([
                "Overview",
                "Forecast",
                "Budget vs Forecast vs Actual",
                "Budget",
                "Variance",
                "Learning Insights",
                "Scenarios",
                "Rolling Forecast",
                "Downloads",
            ])

            with tabs[0]:
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("### Forecast Trend")
                    if forecast_df is not None and "ds" in forecast_df.columns and "yhat" in forecast_df.columns:
                        chart_df = forecast_df.copy()
                        chart_df["ds"] = pd.to_datetime(chart_df["ds"])
                        chart_df = chart_df.sort_values("ds")
                        st.line_chart(chart_df.set_index("ds")["yhat"])
                    else:
                        st.info("No forecast chart available.")

                with col2:
                    st.markdown("### Budget vs Forecast")
                    if budget_df is not None and forecast_df is not None:
                        b = budget_df.copy()
                        f = forecast_df.copy()
                        if "ds" in b.columns and "ds" in f.columns and "budget" in b.columns and "yhat" in f.columns:
                            b["ds"] = pd.to_datetime(b["ds"])
                            f["ds"] = pd.to_datetime(f["ds"])
                            merged = b.merge(f[["ds", "yhat"]], on="ds", how="inner")
                            if len(merged) > 0:
                                merged = merged.sort_values("ds").set_index("ds")[["budget", "yhat"]]
                                st.line_chart(merged)
                            else:
                                st.info("No merged budget/forecast data available.")
                        else:
                            st.info("Budget/forecast chart columns missing.")
                    else:
                        st.info("Budget or forecast data not found.")

            with tabs[1]:
                if forecast_df is not None:
                    st.dataframe(forecast_df, use_container_width=True)
                else:
                    st.info("forecast.csv not found.")

            with tabs[2]:
                if bfa_df is not None:
                    st.dataframe(bfa_df, use_container_width=True)
                else:
                    st.info("BvFvA output not found.")

            with tabs[3]:
                if budget_df is not None:
                    st.dataframe(budget_df, use_container_width=True)
                else:
                    st.info("budget.csv not found.")

            with tabs[4]:
                if variance_df is not None:
                    st.dataframe(variance_df, use_container_width=True)

                    if "ds" in variance_df.columns and "fc_var_pct" in variance_df.columns:
                        chart_df = variance_df.copy()
                        chart_df["ds"] = pd.to_datetime(chart_df["ds"])
                        chart_df = chart_df.sort_values("ds").set_index("ds")
                        st.markdown("### Forecast Variance % Trend")
                        st.line_chart(chart_df["fc_var_pct"])
                else:
                    st.info("variance.csv not found.")

            with tabs[5]:
                if learning_summary_df is not None:
                    st.markdown("### Learning Summary")
                    st.dataframe(learning_summary_df, use_container_width=True)

                if learning_flags_df is not None:
                    st.markdown("### Learning Flags")
                    st.dataframe(learning_flags_df, use_container_width=True)

                if learning_summary_df is None and learning_flags_df is None:
                    st.info("No learning outputs found.")

            with tabs[6]:
                if scenarios_df is not None:
                    st.dataframe(scenarios_df, use_container_width=True)
                else:
                    st.info("scenarios.csv not found.")

            with tabs[7]:
                if rolling_df is not None:
                    st.dataframe(rolling_df, use_container_width=True)

                    if "forecast_date" in rolling_df.columns and "pct_error" in rolling_df.columns:
                        rdf = rolling_df.copy()
                        rdf["forecast_date"] = pd.to_datetime(rdf["forecast_date"])
                        rdf = rdf.sort_values("forecast_date").set_index("forecast_date")
                        st.markdown("### Rolling Forecast Error %")
                        st.line_chart(rdf["pct_error"])
                else:
                    st.info("rolling_forecast.csv not found.")

            with tabs[8]:
                files_to_offer = [
                    ("planning_bundle.xlsx", "Download Excel Bundle"),
                    ("forecast.csv", "Download Forecast CSV"),
                    ("budget.csv", "Download Budget CSV"),
                    ("budget_forecast_actual_monthly.csv", "Download Monthly BvFvA CSV"),
                    ("variance.csv", "Download Variance CSV"),
                    ("learning_summary.csv", "Download Learning Summary CSV"),
                    ("learning_flags.csv", "Download Learning Flags CSV"),
                ]

                any_file = False
                for fname, label in files_to_offer:
                    fpath = Path(out_dir) / fname
                    if fpath.exists():
                        any_file = True
                        with open(fpath, "rb") as f:
                            st.download_button(
                                label=label,
                                data=f.read(),
                                file_name=fname,
                                mime="application/octet-stream",
                            )

                if not any_file:
                    st.info("No downloadable files found.")

    except Exception as e:
        st.error(f"Run failed: {e}")
else:
    st.info("Upload a file to begin.")