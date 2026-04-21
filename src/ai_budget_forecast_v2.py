import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
from datetime import datetime
import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="AI Budget & Rolling Forecast",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("AI Budget & Rolling Forecasting Framework")
st.markdown("Upload historical data → AI automatically learns seasonality and generates Budget + Rolling Forecast")

# ====================== DYNAMIC SEASONALITY ======================
def learn_dynamic_seasonality(ts):
    ts = ts.copy()
    ts['ds'] = pd.to_datetime(ts['ds'])
    ts['month'] = ts['ds'].dt.month
    
    monthly_avg = ts.groupby('month')['y'].mean()
    overall_avg = ts['y'].mean()
    
    seasonality_index = (monthly_avg / overall_avg).round(3)
    std = seasonality_index.std()
    
    high_months = seasonality_index[seasonality_index > 1 + std*0.7].index.tolist()
    low_months  = seasonality_index[seasonality_index < 1 - std*0.7].index.tolist()
    
    monthly_impact = {}
    for m in range(1, 13):
        if m in monthly_avg:
            monthly_impact[m] = round(((monthly_avg[m] / overall_avg) - 1) * 100, 1)
    
    return {
        "seasonality_index": seasonality_index,
        "high_months": high_months,
        "low_months": low_months,
        "monthly_impact": monthly_impact,
        "overall_avg": round(overall_avg, 2)
    }

# ====================== AUTO BUDGET GENERATION ======================
def generate_auto_budget(forecast_df, seasonal_info, growth_rate=0.08):
    budget_list = []
    for _, row in forecast_df.iterrows():
        m = int(row['month_num'])
        base = seasonal_info['overall_avg'] * (1 + growth_rate)
        factor = seasonal_info['seasonality_index'].get(m, 1.0)
        
        auto_budget = round(base * factor, 0)
        
        budget_list.append({
            "Month": row["Month"],
            "Auto Budget": auto_budget,
            "Forecast": row["Forecast"],
            "Variance %": round((row["Forecast"] - auto_budget) / auto_budget * 100, 1)
        })
    return pd.DataFrame(budget_list)

# ====================== FORECAST FUNCTION ======================
def run_ai_forecast(ts, forecast_months=12):
    seasonal_info = learn_dynamic_seasonality(ts)
    
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode='multiplicative',
        changepoint_prior_scale=0.12
    )
    model.fit(ts)
    
    future = model.make_future_dataframe(periods=forecast_months, freq='MS')
    forecast = model.predict(future)
    
    last_date = ts['ds'].max()
    fc = forecast[forecast['ds'] > last_date].head(forecast_months).copy()
    
    result = pd.DataFrame({
        "Month": fc["ds"],
        "Low": fc["yhat_lower"].clip(lower=0).round(0),
        "Forecast": fc["yhat"].clip(lower=0).round(0),
        "High": fc["yhat_upper"].clip(lower=0).round(0),
        "month_num": fc["ds"].dt.month
    })
    
    result["Learned Impact %"] = result["month_num"].map(seasonal_info["monthly_impact"])
    result["Month"] = result["Month"].dt.strftime("%Y-%m")
    
    return result, seasonal_info

# ====================== MAIN APP ======================
uploaded_file = st.file_uploader("Upload Historical Data (CSV or Excel)", 
                                type=["csv", "xlsx", "xls"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        st.success(f"File loaded successfully - {len(df):,} rows and {len(df.columns)} columns")
        
        col1, col2 = st.columns(2)
        with col1:
            date_col = st.selectbox("Date Column", df.columns)
        with col2:
            value_col = st.selectbox("Value Column (Revenue / Rentals / Amount)", df.columns)
        
        ts = df[[date_col, value_col]].copy()
        ts.columns = ["ds", "y"]
        ts = ts.dropna()
        ts['ds'] = pd.to_datetime(ts['ds'])
        ts = ts.sort_values('ds').reset_index(drop=True)
        
        forecast_months = st.slider("Forecast Period (Months)", 6, 24, 12)
        
        if st.button("Generate Auto Budget & Rolling Forecast", type="primary"):
            with st.spinner("AI is analyzing historical patterns..."):
                
                forecast_df, seasonal_info = run_ai_forecast(ts, forecast_months)
                budget_df = generate_auto_budget(forecast_df, seasonal_info)
                
                # Results
                st.subheader("AI Learned Seasonality")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**High Demand Months:**", seasonal_info['high_months'])
                with c2:
                    st.write("**Low Demand Months:**", seasonal_info['low_months'])
                
                st.subheader("Auto Budget vs Forecast")
                st.dataframe(
                    budget_df.style.format({
                        "Auto Budget": "{:,.0f}",
                        "Forecast": "{:,.0f}",
                        "Variance %": "{:+.1f}%"
                    }),
                    use_container_width=True
                )
                
                # Download Excel
                # (Excel builder can be expanded later)
                csv = budget_df.to_csv(index=False)
                st.download_button(
                    label="Download Report as CSV",
                    data=csv,
                    file_name=f"AI_Budget_Forecast_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
                
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")

else:
    st.info("Please upload your historical monthly data to begin.")