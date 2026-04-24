import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app_service import run_forecasting_app
from datetime import date

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

    if "custom_events" not in st.session_state:
        st.session_state["custom_events"] = []

    with st.expander("Add Custom Events", expanded=False):
        event_name = st.text_input("Event Name", placeholder="Summer Campaign")
        event_start = st.date_input("Start Date", value=date.today())
        event_end = st.date_input("End Date", value=date.today())

        if st.button("Add Event"):
            if not event_name.strip():
                st.warning("Please enter an event name.")
            elif event_end < event_start:
                st.warning("End date cannot be before start date.")
            else:
                st.session_state["custom_events"].append({
                    "name": event_name.strip(),
                    "start_date": event_start.isoformat(),
                    "end_date": event_end.isoformat(),
                })
                st.success("Event added.")

        if st.session_state["custom_events"]:
            st.markdown("**Added Events**")
            st.dataframe(pd.DataFrame(st.session_state["custom_events"]), use_container_width=True)

            if st.button("Clear Events"):
                st.session_state["custom_events"] = []
                st.success("Custom events cleared.")


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

            if st.button("Run Model", type="primary"):
                with st.spinner("Running budget forecasting Model... please wait."):
                    saved_path = save_uploaded_file(uploaded_file)
                    # custom_events = parse_custom_events(custom_events_text)
                    custom_events = st.session_state.get("custom_events", [])

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

                st.success("Automate Budgeting & Forecasting completed successfully.")

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

            st.subheader("Dashboard")
            st.caption(
                    f"Metric: {value_column} | Horizon: {forecast_period} months | "
                    f"Breakdown: {breakdown_level} | "
                    f"Events: Ramzan={'On' if include_ramzan else 'Off'}, "
                    f"Eid={'On' if include_eid else 'Off'}, "
                    f"Custom={len(st.session_state.get('custom_events', []))}"
            )

            # KPI values
            forecast_mae = safe_mean(learning_summary_df, "forecast_mae")
            forecast_bias = safe_mean(learning_summary_df, "forecast_bias_pct")
            latest_budget = safe_latest(budget_df, "budget")
            latest_forecast = safe_latest(forecast_df, "yhat")

            def fmt_money(value):
                if value is None:
                    return "N/A"
                return f"{value / 1_000_000:.2f}M"

            def fmt_pct(value):
                if value is None:
                    return "N/A"
                return f"{value:.1f}%"

            c1, c2, c3, c4 = st.columns(4)

            with c1:
                st.metric("Latest Forecast", fmt_money(latest_forecast))

            with c2:
                st.metric("Latest Budget", fmt_money(latest_budget))

            with c3:
                st.metric("Forecast MAE", fmt_money(forecast_mae))

            with c4:
                st.metric("Forecast Bias", fmt_pct(forecast_bias))

            st.markdown("### Key Insights")

            insight_msgs = get_learning_message(learning_flags_df)

            if forecast_bias is not None:
                if forecast_bias > 15:
                    insight_msgs.append(
                        "Forecast has historically been conservative. Actuals were higher than forecast."
                    )
                elif forecast_bias < -15:
                    insight_msgs.append(
                        "Forecast has historically been aggressive. Actuals were lower than forecast."
                    )
                else:
                    insight_msgs.append("Forecast bias is within a reasonable range.")

            if insight_msgs:
                for msg in insight_msgs[:4]:
                    st.info(msg)
            else:
                st.info("No major risks detected from the latest run.")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Forecast Trend")
                if forecast_df is not None and "ds" in forecast_df.columns and "yhat" in forecast_df.columns:
                    chart_df = forecast_df.copy()
                    chart_df["ds"] = pd.to_datetime(chart_df["ds"])
                    chart_df = chart_df.sort_values("ds").set_index("ds")
                    st.line_chart(chart_df["yhat"])
                else:
                    st.info("Forecast chart not available.")

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
                            merged = merged.sort_values("ds").set_index("ds")
                            merged = merged.rename(columns={"yhat": "forecast"})
                            st.line_chart(merged[["budget", "forecast"]])
                        else:
                            st.info("Budget vs Forecast chart not available.")
                    else:
                        st.info("Budget vs Forecast chart columns missing.")
                else:
                    st.info("Budget or forecast data not found.")

            st.markdown("### Monthly Planning Summary")

            if bfa_df is not None:
                display_df = bfa_df.copy()

                preferred_cols = [
                    "period",
                    "series",
                    "actual",
                    "forecast",
                    "budget",
                    "actual_vs_forecast",
                    "actual_vs_budget",
                    "budget_vs_forecast",
                ]

                cols = [c for c in preferred_cols if c in display_df.columns]
                display_df = display_df[cols]

                display_df = display_df.rename(columns={
                    "period": "Month",
                    "series": "Segment",
                    "actual": "Actual",
                    "forecast": "Forecast",
                    "budget": "Budget",
                    "actual_vs_forecast": "Actual vs Forecast",
                    "actual_vs_budget": "Actual vs Budget",
                    "budget_vs_forecast": "Budget vs Forecast",
                })

                st.dataframe(display_df, use_container_width=True)
            else:
                st.info("Monthly planning summary not available.")

            st.markdown("### Export")

            excel_path = Path(out_dir) / "planning_bundle.xlsx"
            if excel_path.exists():
                with open(excel_path, "rb") as f:
                    st.download_button(
                        label="Download Excel Report",
                        data=f.read(),
                        file_name="planning_bundle.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            else:
                st.info("Excel report not available.")

    except Exception as e:
        st.error(f"Run failed: {e}")
else:
    st.info("Upload a file to begin.")