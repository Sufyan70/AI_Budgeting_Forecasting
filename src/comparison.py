from __future__ import annotations

import pandas as pd


def merge_bfa(
    actuals: pd.DataFrame,
    forecast: pd.DataFrame,
    budget: pd.DataFrame | None = None,
    series_key: str = "Total",
) -> pd.DataFrame:
    out = actuals[["ds", "y"]].copy().rename(columns={"y": "actual"})
    out["series"] = series_key

    if forecast is not None and len(forecast) > 0:
        f = forecast.copy()
        cols = [c for c in ["ds", "yhat", "raw_yhat", "calibration_multiplier", "series"] if c in f.columns]
        f = f[cols].rename(columns={"yhat": "forecast", "raw_yhat": "raw_forecast"})
        if "series" not in f.columns:
            f["series"] = series_key
        out = out.merge(f, on=["ds", "series"], how="outer")

    if budget is not None and len(budget) > 0:
        b = budget.copy()
        if "budget" not in b.columns and "budget_amount" in b.columns:
            b = b.rename(columns={"budget_amount": "budget"})
        if "series" not in b.columns:
            b["series"] = series_key
        out = out.merge(b[["ds", "series", "budget"]], on=["ds", "series"], how="outer")

    out["series"] = out["series"].fillna(series_key)
    out["actual"] = pd.to_numeric(out.get("actual"), errors="coerce")
    if "forecast" in out.columns:
        out["forecast"] = pd.to_numeric(out["forecast"], errors="coerce")
    if "budget" in out.columns:
        out["budget"] = pd.to_numeric(out["budget"], errors="coerce")
    if "raw_forecast" in out.columns:
        out["raw_forecast"] = pd.to_numeric(out["raw_forecast"], errors="coerce")
    if "calibration_multiplier" in out.columns:
        out["calibration_multiplier"] = pd.to_numeric(out["calibration_multiplier"], errors="coerce")

    out = out.sort_values("ds").reset_index(drop=True)

    if "forecast" in out.columns:
        out["actual_vs_forecast"] = out["actual"] - out["forecast"]
        out["actual_vs_forecast_pct"] = (
            out["actual_vs_forecast"] / out["forecast"].abs().clip(lower=1) * 100
        )

    if "budget" in out.columns:
        out["actual_vs_budget"] = out["actual"] - out["budget"]
        out["actual_vs_budget_pct"] = (
            out["actual_vs_budget"] / out["budget"].abs().clip(lower=1) * 100
        )

    if "forecast" in out.columns and "budget" in out.columns:
        out["budget_vs_forecast"] = out["budget"] - out["forecast"]
        out["budget_vs_forecast_pct"] = (
            out["budget_vs_forecast"] / out["forecast"].abs().clip(lower=1) * 100
        )

    return out


def build_monthly_bfa_table(bfa: pd.DataFrame) -> pd.DataFrame:
    out = bfa.copy()
    out["ds"] = pd.to_datetime(out["ds"], errors="coerce")
    out = out.dropna(subset=["ds"])

    out["period"] = out["ds"].dt.to_period("M").astype(str)
    if "series" not in out.columns:
        out["series"] = "Total"
    out["series"] = out["series"].fillna("Total")

    numeric_cols = [
        c for c in [
            "actual",
            "forecast",
            "budget",
            "raw_forecast",
            "actual_vs_forecast",
            "actual_vs_budget",
            "budget_vs_forecast",
        ]
        if c in out.columns
    ]

    for c in numeric_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    group_cols = ["period", "series"]
    monthly = out.groupby(group_cols, dropna=False)[numeric_cols].sum(min_count=1).reset_index()

    ordered_cols = ["period", "series"] + numeric_cols
    return monthly[ordered_cols]


def compute_kpis(bfa: pd.DataFrame) -> dict:
    kpis = {}

    if "forecast" in bfa.columns:
        valid = bfa[["actual", "forecast"]].dropna()
        if len(valid) > 0:
            e = (valid["actual"] - valid["forecast"]).abs()
            denom = valid["forecast"].abs().clip(lower=1)
            kpis["fc_mae"] = float(e.mean())
            kpis["fc_mape"] = float((e / denom * 100).mean())
        else:
            kpis["fc_mae"] = None
            kpis["fc_mape"] = None

    if "budget" in bfa.columns:
        valid = bfa[["actual", "budget"]].dropna()
        if len(valid) > 0:
            e = (valid["actual"] - valid["budget"]).abs()
            denom = valid["budget"].abs().clip(lower=1)
            kpis["budget_mae"] = float(e.mean())
            kpis["budget_mape"] = float((e / denom * 100).mean())
        else:
            kpis["budget_mae"] = None
            kpis["budget_mape"] = None

    return kpis