import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import io

# ─── Page Config ───
st.set_page_config(
    page_title="BudgetCast AI · Forecasting Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Custom CSS ───
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,500;0,9..40,700;1,9..40,400&family=Space+Mono:wght@400;700&display=swap');

:root {
    --bg-primary: #0a0e17;
    --bg-card: #111827;
    --bg-card-hover: #1a2332;
    --accent-blue: #3b82f6;
    --accent-cyan: #06b6d4;
    --accent-emerald: #10b981;
    --accent-amber: #f59e0b;
    --accent-rose: #f43f5e;
    --accent-violet: #8b5cf6;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --border-color: #1e293b;
}

.stApp {
    background: linear-gradient(135deg, #0a0e17 0%, #0f172a 50%, #0a0e17 100%);
}

.main .block-container {
    padding-top: 2rem;
    max-width: 1400px;
}

h1, h2, h3 {
    font-family: 'DM Sans', sans-serif !important;
    color: var(--text-primary) !important;
}

.stMetric label {
    font-family: 'DM Sans', sans-serif !important;
    color: var(--text-secondary) !important;
}

.stMetric [data-testid="stMetricValue"] {
    font-family: 'Space Mono', monospace !important;
    color: var(--accent-cyan) !important;
}

div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    border-right: 1px solid var(--border-color);
}

.metric-card {
    background: linear-gradient(135deg, #111827 0%, #1e293b 100%);
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 12px;
    transition: all 0.3s ease;
}
.metric-card:hover {
    border-color: #3b82f6;
    box-shadow: 0 0 20px rgba(59, 130, 246, 0.1);
}
.metric-label {
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 6px;
}
.metric-value {
    font-family: 'Space Mono', monospace;
    font-size: 28px;
    font-weight: 700;
    background: linear-gradient(90deg, #06b6d4, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.metric-delta {
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    margin-top: 4px;
}
.delta-positive { color: #10b981; }
.delta-negative { color: #f43f5e; }

.header-banner {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #1e293b;
    border-radius: 16px;
    padding: 30px 40px;
    margin-bottom: 30px;
    position: relative;
    overflow: hidden;
}
.header-banner::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #3b82f6, #06b6d4, #10b981);
}
.header-title {
    font-family: 'DM Sans', sans-serif;
    font-size: 32px;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0;
}
.header-sub {
    font-family: 'DM Sans', sans-serif;
    font-size: 14px;
    color: #64748b;
    margin-top: 6px;
    letter-spacing: 0.5px;
}

.event-tag {
    display: inline-block;
    background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-family: 'DM Sans', sans-serif;
    margin: 2px 4px;
}

.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #1e293b, transparent);
    margin: 30px 0;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: transparent;
}
.stTabs [data-baseweb="tab"] {
    background-color: #111827;
    border-radius: 8px;
    color: #94a3b8;
    border: 1px solid #1e293b;
    padding: 8px 20px;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%) !important;
    color: white !important;
    border-color: transparent !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ───
if "data" not in st.session_state:
    st.session_state.data = None
if "events" not in st.session_state:
    st.session_state.events = []
if "forecast_result" not in st.session_state:
    st.session_state.forecast_result = None
if "budget_result" not in st.session_state:
    st.session_state.budget_result = None

# ─── Helper Functions ───

def format_currency(val, prefix="Rs. "):
    if abs(val) >= 1_000_000:
        return f"{prefix}{val/1_000_000:,.2f}M"
    elif abs(val) >= 1_000:
        return f"{prefix}{val/1_000:,.1f}K"
    return f"{prefix}{val:,.0f}"

def detect_date_column(df):
    """Auto-detect the date/time column."""
    for col in df.columns:
        if df[col].dtype == 'object':
            try:
                pd.to_datetime(df[col])
                return col
            except:
                pass
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    return None

def detect_numeric_columns(df):
    """Get all numeric columns."""
    return df.select_dtypes(include=[np.number]).columns.tolist()

def prepare_time_series(df, date_col, value_col):
    """Prepare a clean monthly time series."""
    ts = df[[date_col, value_col]].copy()
    ts[date_col] = pd.to_datetime(ts[date_col])
    ts = ts.sort_values(date_col)
    ts = ts.set_index(date_col)
    ts = ts.resample('MS').sum()
    ts = ts.fillna(method='ffill').fillna(0)
    return ts

def calculate_seasonality(ts, periods=12):
    """Extract seasonal pattern from time series."""
    values = ts.values.flatten()
    if len(values) < periods:
        return np.ones(periods)
    n_full = len(values) // periods
    if n_full == 0:
        pattern = values / (np.mean(values) if np.mean(values) != 0 else 1)
        pattern = np.pad(pattern, (0, periods - len(pattern)), constant_values=1.0)
        return pattern
    seasonal = np.zeros(periods)
    for i in range(periods):
        month_vals = [values[j * periods + i] for j in range(n_full) if j * periods + i < len(values)]
        seasonal[i] = np.mean(month_vals) if month_vals else 0
    overall_mean = np.mean(values[:n_full * periods])
    if overall_mean != 0:
        seasonal = seasonal / overall_mean
    else:
        seasonal = np.ones(periods)
    return seasonal

def detect_trend(ts):
    """Detect linear trend using OLS."""
    values = ts.values.flatten()
    x = np.arange(len(values))
    if len(values) < 2:
        return 0, values[0] if len(values) > 0 else 0
    A = np.vstack([x, np.ones(len(x))]).T
    try:
        slope, intercept = np.linalg.lstsq(A, values, rcond=None)[0]
    except:
        slope, intercept = 0, np.mean(values)
    return slope, intercept

def apply_events(forecast_df, events, date_col='date'):
    """Apply event-based adjustments to forecast."""
    adjusted = forecast_df.copy()
    for event in events:
        evt_start = pd.to_datetime(event['start_date'])
        evt_end = pd.to_datetime(event['end_date'])
        impact = event['impact_pct'] / 100.0
        mask = (adjusted[date_col] >= evt_start) & (adjusted[date_col] <= evt_end)
        for col in adjusted.columns:
            if col != date_col and pd.api.types.is_numeric_dtype(adjusted[col]):
                adjusted.loc[mask, col] = adjusted.loc[mask, col] * (1 + impact)
    return adjusted

def generate_forecast(ts, forecast_months, events=[], method="ai_composite"):
    """
    AI Composite Forecasting Engine:
    - Trend extraction (linear regression)
    - Seasonality decomposition
    - Weighted moving average smoothing
    - Event impact overlay
    - Confidence intervals via residual analysis
    """
    values = ts.values.flatten()
    dates = ts.index

    # Trend
    slope, intercept = detect_trend(ts)

    # Seasonality
    seasonal = calculate_seasonality(ts, 12)

    # Weighted moving average (recent data weighted more)
    if len(values) >= 3:
        weights = np.exp(np.linspace(-1, 0, min(len(values), 12)))
        weights /= weights.sum()
        wma_base = np.average(values[-min(len(values), 12):], weights=weights[-min(len(values), 12):] if len(weights) >= min(len(values), 12) else weights)
    else:
        wma_base = np.mean(values)

    # Generate forecast
    last_date = dates[-1]
    forecast_dates = [last_date + relativedelta(months=i+1) for i in range(forecast_months)]
    forecast_values = []
    residuals = values - (slope * np.arange(len(values)) + intercept)
    residual_std = np.std(residuals) if len(residuals) > 1 else np.mean(values) * 0.1

    for i in range(forecast_months):
        t = len(values) + i
        trend_component = slope * t + intercept
        month_idx = forecast_dates[i].month - 1
        season_factor = seasonal[month_idx]

        if method == "ai_composite":
            # Blend trend-projected and WMA-based
            trend_forecast = trend_component * season_factor
            wma_forecast = wma_base * season_factor * (1 + slope / (np.mean(values) if np.mean(values) != 0 else 1)) ** (i / 12)
            blended = 0.6 * trend_forecast + 0.4 * wma_forecast
        elif method == "trend_only":
            blended = trend_component
        elif method == "seasonal_only":
            blended = np.mean(values) * season_factor
        else:
            blended = trend_component * season_factor

        forecast_values.append(max(0, blended))

    forecast_df = pd.DataFrame({
        'date': forecast_dates,
        'forecast': forecast_values,
        'lower_bound': [max(0, v - 1.96 * residual_std * (1 + 0.05 * i)) for i, v in enumerate(forecast_values)],
        'upper_bound': [v + 1.96 * residual_std * (1 + 0.05 * i) for i, v in enumerate(forecast_values)]
    })

    # Apply events
    if events:
        forecast_df = apply_events(forecast_df, events, 'date')
        forecast_df['lower_bound'] = apply_events(
            pd.DataFrame({'date': forecast_df['date'], 'lower_bound': forecast_df['lower_bound']}),
            events, 'date'
        )['lower_bound']
        forecast_df['upper_bound'] = apply_events(
            pd.DataFrame({'date': forecast_df['date'], 'upper_bound': forecast_df['upper_bound']}),
            events, 'date'
        )['upper_bound']

    return forecast_df

def generate_budget(ts, forecast_df, budget_method, growth_target=0.0, custom_allocations=None):
    """Generate budget based on forecast + user preferences."""
    budget_df = forecast_df[['date', 'forecast']].copy()
    budget_df = budget_df.rename(columns={'forecast': 'budget'})

    if budget_method == "Growth Target":
        budget_df['budget'] = budget_df['budget'] * (1 + growth_target / 100)
    elif budget_method == "Conservative (90%)":
        budget_df['budget'] = budget_df['budget'] * 0.90
    elif budget_method == "Aggressive (110%)":
        budget_df['budget'] = budget_df['budget'] * 1.10
    elif budget_method == "Zero-Based":
        base = ts.values.flatten()[-1] if len(ts) > 0 else 0
        budget_df['budget'] = base

    if custom_allocations:
        for month, alloc in custom_allocations.items():
            mask = budget_df['date'].dt.month == month
            budget_df.loc[mask, 'budget'] = alloc

    return budget_df

def rolling_forecast(ts, window_months=3, forecast_ahead=12, events=[]):
    """Rolling forecast: re-forecast every window using latest data."""
    values = ts.values.flatten()
    dates = ts.index
    results = []

    for start in range(0, len(values), window_months):
        end = min(start + window_months, len(values))
        subset = ts.iloc[:end]
        fc = generate_forecast(subset, forecast_ahead, events)
        fc['roll_window'] = f"Window {start//window_months + 1}"
        fc['window_end_date'] = dates[end - 1]
        results.append(fc)

    return results

def compute_variance(actual_df, budget_df, date_col='date', actual_col='actual', budget_col='budget'):
    """Compute variance analysis."""
    merged = pd.merge(actual_df, budget_df, on=date_col, how='inner')
    merged['variance'] = merged[actual_col] - merged[budget_col]
    merged['variance_pct'] = np.where(
        merged[budget_col] != 0,
        (merged['variance'] / merged[budget_col]) * 100,
        0
    )
    merged['status'] = merged['variance'].apply(
        lambda x: '✅ Favorable' if x >= 0 else '⚠️ Unfavorable'
    )
    return merged


# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 20px 0;">
        <div style="font-family: 'Space Mono', monospace; font-size: 24px; font-weight: 700;
                    background: linear-gradient(90deg, #3b82f6, #06b6d4);
                    -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            📊 BudgetCast AI
        </div>
        <div style="font-family: 'DM Sans', sans-serif; font-size: 11px; color: #64748b;
                    letter-spacing: 2px; text-transform: uppercase; margin-top: 4px;">
            Forecasting Engine
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ─── Data Upload ───
    st.markdown("##### 📁 Data Upload")
    uploaded_file = st.file_uploader(
        "Upload your financial data",
        type=["csv", "xlsx", "xls"],
        help="CSV or Excel file with date column and numeric values"
    )

    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            st.session_state.data = df
            st.success(f"✅ {len(df)} rows loaded")
        except Exception as e:
            st.error(f"Error: {e}")

    st.markdown("---")

    # ─── Column Selection ───
    if st.session_state.data is not None:
        df = st.session_state.data
        st.markdown("##### ⚙️ Configuration")

        date_col = detect_date_column(df)
        all_cols = df.columns.tolist()
        date_col_selected = st.selectbox(
            "Date Column",
            all_cols,
            index=all_cols.index(date_col) if date_col in all_cols else 0
        )

        numeric_cols = detect_numeric_columns(df)
        if numeric_cols:
            value_col = st.selectbox("Value Column (Revenue/Sales/etc.)", numeric_cols)
        else:
            st.warning("No numeric columns found!")
            value_col = None

        st.markdown("---")

        # ─── Forecast Settings ───
        st.markdown("##### 🔮 Forecast Settings")
        forecast_period = st.selectbox(
            "Forecast Horizon",
            ["6 Months", "1 Year", "2 Years", "3 Years", "Custom"],
            index=1
        )
        if forecast_period == "Custom":
            forecast_months = st.slider("Months", 1, 60, 12)
        else:
            forecast_months = {"6 Months": 6, "1 Year": 12, "2 Years": 24, "3 Years": 36}[forecast_period]

        forecast_method = st.selectbox(
            "Forecasting Method",
            ["AI Composite (Recommended)", "Trend Only", "Seasonal Only"],
            help="AI Composite blends trend + seasonality + weighted moving average"
        )
        method_map = {
            "AI Composite (Recommended)": "ai_composite",
            "Trend Only": "trend_only",
            "Seasonal Only": "seasonal_only"
        }

        st.markdown("---")

        # ─── Budget Settings ───
        st.markdown("##### 💰 Budget Settings")
        budget_method = st.selectbox(
            "Budget Strategy",
            ["Forecast-Based", "Growth Target", "Conservative (90%)", "Aggressive (110%)", "Zero-Based"]
        )
        growth_target = 0.0
        if budget_method == "Growth Target":
            growth_target = st.slider("Growth Target %", -20.0, 50.0, 10.0, 0.5)

        st.markdown("---")

        # ─── Rolling Forecast ───
        st.markdown("##### 🔄 Rolling Forecast")
        enable_rolling = st.checkbox("Enable Rolling Forecast", value=False)
        if enable_rolling:
            roll_window = st.slider("Rolling Window (months)", 1, 12, 3)
        else:
            roll_window = 3


# ═══════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════

# Header
st.markdown("""
<div class="header-banner">
    <p class="header-title">BudgetCast AI · Forecasting Engine</p>
    <p class="header-sub">AI-POWERED BUDGETING · SEASONALITY-AWARE FORECASTING · EVENT-DRIVEN PLANNING</p>
</div>
""", unsafe_allow_html=True)

if st.session_state.data is None:
    # Landing / Empty State
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Step 1</div>
            <div style="font-size:18px; color:#f1f5f9; font-family:'DM Sans',sans-serif; font-weight:500;">
                📁 Upload Data
            </div>
            <div style="font-size:13px; color:#64748b; margin-top:8px; font-family:'DM Sans',sans-serif;">
                CSV or Excel file with dates and financial metrics
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Step 2</div>
            <div style="font-size:18px; color:#f1f5f9; font-family:'DM Sans',sans-serif; font-weight:500;">
                🎯 Add Events
            </div>
            <div style="font-size:13px; color:#64748b; margin-top:8px; font-family:'DM Sans',sans-serif;">
                Ramzan, Peak Season, promotions, or custom business events
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">Step 3</div>
            <div style="font-size:18px; color:#f1f5f9; font-family:'DM Sans',sans-serif; font-weight:500;">
                📊 Get Results
            </div>
            <div style="font-size:13px; color:#64748b; margin-top:8px; font-family:'DM Sans',sans-serif;">
                Budget, Forecast, Rolling Forecast, Variance Analysis & more
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

    # Sample data generator
    st.markdown("#### 🧪 No data? Generate sample data to try it out")
    if st.button("Generate Sample Data", type="primary"):
        np.random.seed(42)
        months = pd.date_range(start='2022-01-01', periods=36, freq='MS')
        base = 500000
        trend = np.linspace(0, 200000, 36)
        seasonal = np.array([0.8, 0.75, 1.2, 1.1, 0.9, 0.85, 0.7, 0.7, 1.0, 1.15, 1.3, 1.5] * 3)
        noise = np.random.normal(0, 30000, 36)
        revenue = (base + trend) * seasonal + noise

        sample_df = pd.DataFrame({
            'date': months,
            'revenue': np.round(revenue, 0),
            'expenses': np.round(revenue * np.random.uniform(0.55, 0.75, 36), 0),
            'marketing_spend': np.round(revenue * np.random.uniform(0.08, 0.15, 36), 0)
        })
        st.session_state.data = sample_df
        st.rerun()

else:
    df = st.session_state.data

    # ─── TABS ───
    tabs = st.tabs(["📈 Forecast & Budget", "🎯 Events & Scenarios", "🔄 Rolling Forecast", "📊 Variance Analysis", "📋 Data Explorer"])

    # ═══════════════════════════════════════
    # TAB 1: FORECAST & BUDGET
    # ═══════════════════════════════════════
    with tabs[0]:
        if value_col:
            ts = prepare_time_series(df, date_col_selected, value_col)

            # KPI Cards
            recent_val = ts.values[-1][0] if len(ts) > 0 else 0
            avg_val = ts.values.mean()
            slope_val, _ = detect_trend(ts)
            trend_dir = "📈" if slope_val > 0 else "📉"
            growth_pct = (slope_val / avg_val * 100) if avg_val != 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Latest Value</div>
                    <div class="metric-value">{format_currency(recent_val)}</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Average</div>
                    <div class="metric-value">{format_currency(avg_val)}</div>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Trend</div>
                    <div class="metric-value">{trend_dir} {growth_pct:+.1f}%</div>
                    <div class="metric-delta {'delta-positive' if slope_val > 0 else 'delta-negative'}">
                        per month
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with c4:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">Data Points</div>
                    <div class="metric-value">{len(ts)}</div>
                    <div class="metric-delta" style="color:#64748b;">months</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

            # Generate forecast
            method_key = method_map[forecast_method]
            forecast_df = generate_forecast(ts, forecast_months, st.session_state.events, method_key)
            st.session_state.forecast_result = forecast_df

            # Generate budget
            budget_df = generate_budget(ts, forecast_df, budget_method, growth_target)
            st.session_state.budget_result = budget_df

            # ─── Main Forecast Chart ───
            st.markdown("#### 🔮 Forecast & Budget Projection")

            fig = go.Figure()

            # Historical
            fig.add_trace(go.Scatter(
                x=ts.index, y=ts.values.flatten(),
                name='Historical',
                line=dict(color='#3b82f6', width=2.5),
                mode='lines+markers',
                marker=dict(size=4)
            ))

            # Confidence Interval
            fig.add_trace(go.Scatter(
                x=list(forecast_df['date']) + list(forecast_df['date'][::-1]),
                y=list(forecast_df['upper_bound']) + list(forecast_df['lower_bound'][::-1]),
                fill='toself',
                fillcolor='rgba(6, 182, 212, 0.1)',
                line=dict(color='rgba(6, 182, 212, 0)'),
                name='95% Confidence',
                showlegend=True
            ))

            # Forecast
            fig.add_trace(go.Scatter(
                x=forecast_df['date'], y=forecast_df['forecast'],
                name='Forecast',
                line=dict(color='#06b6d4', width=2.5, dash='dash'),
                mode='lines+markers',
                marker=dict(size=5, symbol='diamond')
            ))

            # Budget
            fig.add_trace(go.Scatter(
                x=budget_df['date'], y=budget_df['budget'],
                name='Budget',
                line=dict(color='#f59e0b', width=2, dash='dot'),
                mode='lines+markers',
                marker=dict(size=5, symbol='square')
            ))

            # Event markers
            for event in st.session_state.events:
                evt_start = pd.to_datetime(event['start_date'])
                fig.add_vrect(
                    x0=evt_start,
                    x1=pd.to_datetime(event['end_date']),
                    fillcolor="rgba(139, 92, 246, 0.1)",
                    layer="below",
                    line_width=1,
                    line_color="rgba(139, 92, 246, 0.3)",
                    annotation_text=event['name'],
                    annotation_position="top left",
                    annotation=dict(font_size=10, font_color="#a78bfa")
                )

            fig.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=500,
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(gridcolor='rgba(30,41,59,0.5)', title=''),
                yaxis=dict(gridcolor='rgba(30,41,59,0.5)', title='', tickformat=',.0f'),
                font=dict(family="DM Sans")
            )
            st.plotly_chart(fig, use_container_width=True)

            # ─── Seasonality Chart ───
            st.markdown("#### 📅 Seasonality Pattern")
            seasonal = calculate_seasonality(ts)
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            colors = ['#f43f5e' if s < 1 else '#10b981' for s in seasonal]

            fig_s = go.Figure(go.Bar(
                x=month_names, y=seasonal,
                marker_color=colors,
                text=[f"{s:.2f}x" for s in seasonal],
                textposition='outside',
                textfont=dict(color='#94a3b8', size=11)
            ))
            fig_s.add_hline(y=1.0, line_dash="dash", line_color="#64748b",
                           annotation_text="Baseline", annotation_position="bottom right")
            fig_s.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(gridcolor='rgba(30,41,59,0.5)', title='Seasonal Factor'),
                xaxis=dict(title=''),
                font=dict(family="DM Sans")
            )
            st.plotly_chart(fig_s, use_container_width=True)

            # Forecast data table
            with st.expander("📋 View Forecast & Budget Data"):
                display_df = pd.merge(forecast_df, budget_df, on='date')
                display_df['date'] = display_df['date'].dt.strftime('%b %Y')
                display_df.columns = ['Month', 'Forecast', 'Lower Bound', 'Upper Bound', 'Budget']
                st.dataframe(display_df.style.format({
                    'Forecast': '{:,.0f}',
                    'Lower Bound': '{:,.0f}',
                    'Upper Bound': '{:,.0f}',
                    'Budget': '{:,.0f}'
                }), use_container_width=True)

                # Download
                csv_buf = io.StringIO()
                display_df.to_csv(csv_buf, index=False)
                st.download_button("⬇️ Download Forecast CSV", csv_buf.getvalue(),
                                  "forecast_budget.csv", "text/csv")

    # ═══════════════════════════════════════
    # TAB 2: EVENTS & SCENARIOS
    # ═══════════════════════════════════════
    with tabs[1]:
        st.markdown("#### 🎯 Event-Driven Scenario Planning")
        st.markdown("""
        <div style="font-family:'DM Sans',sans-serif; color:#94a3b8; font-size:14px; margin-bottom:20px;">
            Add business events that impact your forecast — seasonal peaks, promotions,
            market events, or custom scenarios. Each event applies a percentage impact
            to the forecast during its duration.
        </div>
        """, unsafe_allow_html=True)

        # Preset events
        st.markdown("##### 🏷️ Quick Add Preset Events")
        preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)

        presets = [
            {"name": "🌙 Ramzan Season", "impact": 25, "duration": 30,
             "desc": "High demand during Ramzan"},
            {"name": "🎄 Year-End Peak", "impact": 30, "duration": 45,
             "desc": "Holiday & year-end shopping surge"},
            {"name": "☀️ Summer Slowdown", "impact": -15, "duration": 60,
             "desc": "Reduced activity in summer months"},
            {"name": "🛍️ Black Friday/Sale", "impact": 40, "duration": 7,
             "desc": "Flash sale event period"}
        ]

        for i, (col, preset) in enumerate(zip([preset_col1, preset_col2, preset_col3, preset_col4], presets)):
            with col:
                st.markdown(f"""
                <div class="metric-card" style="padding:15px; text-align:center;">
                    <div style="font-size:24px;">{preset['name'].split(' ')[0]}</div>
                    <div style="font-size:13px; color:#f1f5f9; font-family:'DM Sans'; font-weight:500; margin-top:4px;">
                        {' '.join(preset['name'].split(' ')[1:])}
                    </div>
                    <div style="font-size:11px; color:#64748b; margin-top:4px;">
                        Impact: {'+' if preset['impact']>0 else ''}{preset['impact']}%
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"Add {' '.join(preset['name'].split(' ')[1:])}", key=f"preset_{i}"):
                    today = datetime.now()
                    st.session_state.events.append({
                        'name': preset['name'],
                        'start_date': today.strftime('%Y-%m-%d'),
                        'end_date': (today + timedelta(days=preset['duration'])).strftime('%Y-%m-%d'),
                        'impact_pct': preset['impact'],
                        'description': preset['desc']
                    })
                    st.rerun()

        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

        # Custom event form
        st.markdown("##### ✏️ Add Custom Event")
        with st.form("event_form"):
            ec1, ec2 = st.columns(2)
            with ec1:
                evt_name = st.text_input("Event Name", placeholder="e.g., Product Launch")
                evt_start = st.date_input("Start Date", value=datetime.now())
                evt_impact = st.slider("Impact on Forecast (%)", -50, 100, 10,
                                      help="Positive = increase, Negative = decrease")
            with ec2:
                evt_desc = st.text_input("Description (optional)", placeholder="Brief description")
                evt_end = st.date_input("End Date", value=datetime.now() + timedelta(days=30))

            submitted = st.form_submit_button("➕ Add Event", type="primary")
            if submitted and evt_name:
                st.session_state.events.append({
                    'name': evt_name,
                    'start_date': evt_start.strftime('%Y-%m-%d'),
                    'end_date': evt_end.strftime('%Y-%m-%d'),
                    'impact_pct': evt_impact,
                    'description': evt_desc
                })
                st.success(f"✅ Event '{evt_name}' added!")
                st.rerun()

        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

        # Active events
        st.markdown("##### 📌 Active Events")
        if st.session_state.events:
            for idx, event in enumerate(st.session_state.events):
                ec1, ec2, ec3 = st.columns([3, 1, 0.5])
                with ec1:
                    impact_color = "#10b981" if event['impact_pct'] > 0 else "#f43f5e"
                    st.markdown(f"""
                    <div class="metric-card" style="padding:12px 16px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <span style="font-family:'DM Sans'; font-size:15px; color:#f1f5f9; font-weight:500;">
                                    {event['name']}
                                </span>
                                <span style="font-family:'Space Mono'; font-size:13px; color:{impact_color}; margin-left:12px;">
                                    {'+' if event['impact_pct']>0 else ''}{event['impact_pct']}%
                                </span>
                            </div>
                            <div style="font-family:'DM Sans'; font-size:12px; color:#64748b;">
                                {event['start_date']} → {event['end_date']}
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with ec3:
                    if st.button("🗑️", key=f"del_evt_{idx}"):
                        st.session_state.events.pop(idx)
                        st.rerun()

            if st.button("🗑️ Clear All Events"):
                st.session_state.events = []
                st.rerun()
        else:
            st.info("No events added yet. Add events above to see their impact on forecasts.")

    # ═══════════════════════════════════════
    # TAB 3: ROLLING FORECAST
    # ═══════════════════════════════════════
    with tabs[2]:
        st.markdown("#### 🔄 Rolling Forecast Analysis")
        st.markdown("""
        <div style="font-family:'DM Sans',sans-serif; color:#94a3b8; font-size:14px; margin-bottom:20px;">
            Rolling forecasts continuously re-forecast using the latest available data window.
            Each window generates a new forecast, allowing you to see how predictions evolve as more data arrives.
        </div>
        """, unsafe_allow_html=True)

        if value_col and enable_rolling:
            ts = prepare_time_series(df, date_col_selected, value_col)
            roll_results = rolling_forecast(ts, roll_window, forecast_months, st.session_state.events)

            # Rolling forecast chart
            fig_roll = go.Figure()

            # Historical
            fig_roll.add_trace(go.Scatter(
                x=ts.index, y=ts.values.flatten(),
                name='Historical',
                line=dict(color='#3b82f6', width=3),
                mode='lines'
            ))

            # Each rolling window forecast
            roll_colors = px.colors.qualitative.Set2
            for i, roll_df in enumerate(roll_results):
                color = roll_colors[i % len(roll_colors)]
                fig_roll.add_trace(go.Scatter(
                    x=roll_df['date'], y=roll_df['forecast'],
                    name=roll_df['roll_window'].iloc[0],
                    line=dict(color=color, width=1.5, dash='dash'),
                    opacity=0.7
                ))

            fig_roll.update_layout(
                template='plotly_dark',
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=500,
                title=dict(text=f"Rolling Forecast (Window: {roll_window} months)", font=dict(size=16, family="DM Sans")),
                margin=dict(l=20, r=20, t=60, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(gridcolor='rgba(30,41,59,0.5)'),
                yaxis=dict(gridcolor='rgba(30,41,59,0.5)', tickformat=',.0f'),
                font=dict(family="DM Sans")
            )
            st.plotly_chart(fig_roll, use_container_width=True)

            # Forecast accuracy across windows
            st.markdown("##### 📊 Rolling Window Comparison")
            comparison_data = []
            for roll_df in roll_results:
                window_name = roll_df['roll_window'].iloc[0]
                comparison_data.append({
                    'Window': window_name,
                    'Avg Forecast': roll_df['forecast'].mean(),
                    'Min Forecast': roll_df['forecast'].min(),
                    'Max Forecast': roll_df['forecast'].max(),
                    'Range': roll_df['forecast'].max() - roll_df['forecast'].min()
                })
            comp_df = pd.DataFrame(comparison_data)
            st.dataframe(comp_df.style.format({
                'Avg Forecast': '{:,.0f}',
                'Min Forecast': '{:,.0f}',
                'Max Forecast': '{:,.0f}',
                'Range': '{:,.0f}'
            }), use_container_width=True)

        elif not enable_rolling:
            st.info("⚡ Enable Rolling Forecast in the sidebar to use this feature.")
        else:
            st.warning("Please select a valid value column first.")

    # ═══════════════════════════════════════
    # TAB 4: VARIANCE ANALYSIS
    # ═══════════════════════════════════════
    with tabs[3]:
        st.markdown("#### 📊 Budget vs Forecast vs Actual — Variance Analysis")

        if value_col and st.session_state.forecast_result is not None and st.session_state.budget_result is not None:
            ts = prepare_time_series(df, date_col_selected, value_col)
            forecast_df = st.session_state.forecast_result
            budget_df = st.session_state.budget_result

            # Use historical as "actual" for variance
            actual_df = pd.DataFrame({
                'date': ts.index,
                'actual': ts.values.flatten()
            }).reset_index(drop=True)

            # If there's overlap between actuals and budget
            # For demo, compare last N months of actuals vs budget extrapolated backwards
            st.markdown("""
            <div style="font-family:'DM Sans'; color:#94a3b8; font-size:14px; margin-bottom:20px;">
                Compare your historical actuals against the budget baseline.
                Upload separate actual data or use historical data as actuals for back-testing.
            </div>
            """, unsafe_allow_html=True)

            # Option to upload actuals
            actual_file = st.file_uploader("Upload Actual Results (optional)", type=["csv", "xlsx"],
                                          key="actual_upload")

            if actual_file:
                try:
                    if actual_file.name.endswith('.csv'):
                        actual_raw = pd.read_csv(actual_file)
                    else:
                        actual_raw = pd.read_excel(actual_file)
                    act_date_col = detect_date_column(actual_raw)
                    act_num_cols = detect_numeric_columns(actual_raw)
                    if act_date_col and act_num_cols:
                        act_val_col = st.selectbox("Select Actual Value Column", act_num_cols, key="act_val")
                        actual_ts = prepare_time_series(actual_raw, act_date_col, act_val_col)
                        actual_df = pd.DataFrame({
                            'date': actual_ts.index,
                            'actual': actual_ts.values.flatten()
                        }).reset_index(drop=True)
                except Exception as e:
                    st.error(f"Error loading actuals: {e}")

            # Back-test: generate budget for historical period
            if len(ts) > 6:
                backtest_budget = ts.values.flatten().mean() * calculate_seasonality(ts)
                n_hist = len(ts)
                budget_hist = np.tile(backtest_budget, (n_hist // 12) + 1)[:n_hist]

                variance_df = pd.DataFrame({
                    'date': ts.index,
                    'actual': ts.values.flatten(),
                    'budget': budget_hist
                })
                variance_df['variance'] = variance_df['actual'] - variance_df['budget']
                variance_df['variance_pct'] = np.where(
                    variance_df['budget'] != 0,
                    (variance_df['variance'] / variance_df['budget']) * 100,
                    0
                )
                variance_df['status'] = variance_df['variance'].apply(
                    lambda x: '✅ Favorable' if x >= 0 else '⚠️ Unfavorable'
                )

                # Variance Chart
                fig_var = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.08,
                    row_heights=[0.6, 0.4],
                    subplot_titles=("Actual vs Budget", "Variance (%)")
                )

                fig_var.add_trace(go.Scatter(
                    x=variance_df['date'], y=variance_df['actual'],
                    name='Actual', line=dict(color='#3b82f6', width=2.5)
                ), row=1, col=1)

                fig_var.add_trace(go.Scatter(
                    x=variance_df['date'], y=variance_df['budget'],
                    name='Budget', line=dict(color='#f59e0b', width=2, dash='dash')
                ), row=1, col=1)

                var_colors = ['#10b981' if v >= 0 else '#f43f5e' for v in variance_df['variance_pct']]
                fig_var.add_trace(go.Bar(
                    x=variance_df['date'], y=variance_df['variance_pct'],
                    name='Variance %', marker_color=var_colors
                ), row=2, col=1)

                fig_var.add_hline(y=0, line_dash="dash", line_color="#64748b", row=2, col=1)

                fig_var.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    height=600,
                    margin=dict(l=20, r=20, t=40, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    font=dict(family="DM Sans")
                )
                fig_var.update_xaxes(gridcolor='rgba(30,41,59,0.5)')
                fig_var.update_yaxes(gridcolor='rgba(30,41,59,0.5)')

                st.plotly_chart(fig_var, use_container_width=True)

                # Summary KPIs
                kc1, kc2, kc3, kc4 = st.columns(4)
                total_actual = variance_df['actual'].sum()
                total_budget = variance_df['budget'].sum()
                total_var = total_actual - total_budget
                total_var_pct = (total_var / total_budget * 100) if total_budget != 0 else 0

                with kc1:
                    st.metric("Total Actual", format_currency(total_actual))
                with kc2:
                    st.metric("Total Budget", format_currency(total_budget))
                with kc3:
                    st.metric("Total Variance", format_currency(total_var),
                             delta=f"{total_var_pct:+.1f}%")
                with kc4:
                    favorable = (variance_df['variance'] >= 0).sum()
                    st.metric("Favorable Months", f"{favorable}/{len(variance_df)}")

                # Detailed table
                with st.expander("📋 Detailed Variance Table"):
                    vt = variance_df.copy()
                    vt['date'] = vt['date'].dt.strftime('%b %Y')
                    vt.columns = ['Month', 'Actual', 'Budget', 'Variance', 'Variance %', 'Status']
                    st.dataframe(vt.style.format({
                        'Actual': '{:,.0f}',
                        'Budget': '{:,.0f}',
                        'Variance': '{:+,.0f}',
                        'Variance %': '{:+.1f}%'
                    }), use_container_width=True)
            else:
                st.warning("Need at least 6 months of data for variance analysis.")
        else:
            st.info("Generate a forecast first (Tab 1) to see variance analysis.")

    # ═══════════════════════════════════════
    # TAB 5: DATA EXPLORER
    # ═══════════════════════════════════════
    with tabs[4]:
        st.markdown("#### 📋 Data Explorer")

        st.markdown("##### Raw Data Preview")
        st.dataframe(df.head(50), use_container_width=True)

        st.markdown(f"**Shape:** {df.shape[0]} rows × {df.shape[1]} columns")

        numeric_cols = detect_numeric_columns(df)
        if numeric_cols:
            st.markdown("##### 📊 Column Statistics")
            st.dataframe(df[numeric_cols].describe().style.format('{:,.2f}'), use_container_width=True)

            st.markdown("##### 📈 Quick Visualization")
            viz_col = st.selectbox("Select column to visualize", numeric_cols, key="viz_col")
            if detect_date_column(df):
                ts_viz = prepare_time_series(df, date_col_selected, viz_col)
                fig_viz = go.Figure()
                fig_viz.add_trace(go.Scatter(
                    x=ts_viz.index, y=ts_viz.values.flatten(),
                    mode='lines+markers',
                    line=dict(color='#8b5cf6', width=2),
                    marker=dict(size=4),
                    fill='tozeroy',
                    fillcolor='rgba(139, 92, 246, 0.1)'
                ))
                fig_viz.update_layout(
                    template='plotly_dark',
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    height=350,
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis=dict(gridcolor='rgba(30,41,59,0.5)'),
                    yaxis=dict(gridcolor='rgba(30,41,59,0.5)', tickformat=',.0f'),
                    font=dict(family="DM Sans")
                )
                st.plotly_chart(fig_viz, use_container_width=True)

        # Export all results
        st.markdown("##### ⬇️ Export All Results")
        if st.session_state.forecast_result is not None:
            export_buf = io.BytesIO()
            with pd.ExcelWriter(export_buf, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Raw Data', index=False)
                if st.session_state.forecast_result is not None:
                    st.session_state.forecast_result.to_excel(writer, sheet_name='Forecast', index=False)
                if st.session_state.budget_result is not None:
                    st.session_state.budget_result.to_excel(writer, sheet_name='Budget', index=False)
                if st.session_state.events:
                    pd.DataFrame(st.session_state.events).to_excel(writer, sheet_name='Events', index=False)
            export_buf.seek(0)
            st.download_button(
                "📥 Download Full Report (Excel)",
                export_buf.getvalue(),
                "budgetcast_report.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("Generate a forecast first to enable full export.")