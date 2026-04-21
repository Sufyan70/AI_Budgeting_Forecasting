from __future__ import annotations

import pandas as pd



def merge_bfa(actuals: pd.DataFrame, forecast: pd.DataFrame, budget: pd.DataFrame | None = None, series_key: str = "Total") -> pd.DataFrame:
    out = actuals[["ds", "y"]].copy().rename(columns={"y": "actual"})
    out["series"] = series_key
    if forecast is not None and len(forecast) > 0:
        f = forecast.copy()
        cols = [c for c in ["ds", "yhat", "raw_yhat", "calibration_multiplier"] if c in f.columns]
        f = f[cols].rename(columns={"yhat": "forecast", "raw_yhat": "raw_forecast"})
        out = out.merge(f, on="ds", how="outer")
    if budget is not None and len(budget) > 0:
        b = budget.copy()
        if "budget" not in b.columns and "budget_amount" in b.columns:
            b = b.rename(columns={"budget_amount": "budget"})
        out = out.merge(b[["ds", "budget"]], on="ds", how="outer")
    out = out.sort_values("ds").reset_index(drop=True)
    if "forecast" in out.columns:
        out["actual_vs_forecast"] = out["actual"] - out["forecast"]
        out["actual_vs_forecast_pct"] = out["actual_vs_forecast"] / out["forecast"].abs().clip(lower=1) * 100
    if "budget" in out.columns:
        out["actual_vs_budget"] = out["actual"] - out["budget"]
        out["actual_vs_budget_pct"] = out["actual_vs_budget"] / out["budget"].abs().clip(lower=1) * 100
    if "forecast" in out.columns and "budget" in out.columns:
        out["budget_vs_forecast"] = out["budget"] - out["forecast"]
        out["budget_vs_forecast_pct"] = out["budget_vs_forecast"] / out["forecast"].abs().clip(lower=1) * 100
    return out



def build_monthly_bfa_table(bfa: pd.DataFrame) -> pd.DataFrame:
    out = bfa.copy()
    out["period"] = pd.to_datetime(out["ds"]).dt.to_period("M").astype(str)
    numeric_cols = [c for c in ["actual", "forecast", "budget", "actual_vs_forecast", "actual_vs_budget", "budget_vs_forecast"] if c in out.columns]
    group_cols = ["period"] + (["series"] if "series" in out.columns else [])
    return out.groupby(group_cols, dropna=False)[numeric_cols].sum().reset_index()



def compute_kpis(bfa: pd.DataFrame) -> dict:
    kpis = {}
    if "forecast" in bfa.columns:
        e = (bfa["actual"] - bfa["forecast"]).abs()
        denom = bfa["forecast"].abs().clip(lower=1)
        kpis["fc_mae"] = float(e.mean()) if len(e.dropna()) else None
        kpis["fc_mape"] = float((e / denom * 100).mean()) if len(e.dropna()) else None
    if "budget" in bfa.columns:
        e = (bfa["actual"] - bfa["budget"]).abs()
        denom = bfa["budget"].abs().clip(lower=1)
        kpis["budget_mae"] = float(e.mean()) if len(e.dropna()) else None
        kpis["budget_mape"] = float((e / denom * 100).mean()) if len(e.dropna()) else None
    return kpis
