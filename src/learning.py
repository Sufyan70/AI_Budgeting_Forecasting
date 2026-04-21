from __future__ import annotations

import os
import pandas as pd


class LearningEngine:

    @staticmethod
    def append_history(
        bfa: pd.DataFrame,
        run_label: str,
        output_dir: str,
        forecast_grain: str = "monthly",
    ) -> str:
        hist = bfa.copy()
        hist["run_label"] = run_label
        hist["forecast_grain"] = forecast_grain
        hist["run_timestamp"] = pd.Timestamp.now()

        path = os.path.join(output_dir, "forecast_history.csv")
        write_header = not os.path.exists(path)

        hist.to_csv(path, mode="a", header=write_header, index=False)
        return path

    @staticmethod
    def analyze_learning(history_df: pd.DataFrame) -> pd.DataFrame:
        df = history_df.copy()

        for col in ["actual", "forecast", "budget"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "actual" in df.columns and "forecast" in df.columns:
            df["forecast_error"] = df["actual"] - df["forecast"]
            df["forecast_error_pct"] = (
                df["forecast_error"] / df["forecast"].abs().clip(lower=1) * 100
            )

        if "actual" in df.columns and "budget" in df.columns:
            df["budget_error"] = df["actual"] - df["budget"]
            df["budget_error_pct"] = (
                df["budget_error"] / df["budget"].abs().clip(lower=1) * 100
            )

        group_cols = ["series"] if "series" in df.columns else []
        if not group_cols:
            df["series"] = "Total"
            group_cols = ["series"]

        summary = (
            df.groupby(group_cols, dropna=False)
            .agg(
                forecast_bias_pct=("forecast_error_pct", "mean"),
                forecast_mae=("forecast_error", lambda s: s.abs().mean()),
                budget_bias_pct=("budget_error_pct", "mean"),
                budget_mae=("budget_error", lambda s: s.abs().mean()),
                observations=("series", "count"),
            )
            .reset_index()
        )

        return summary

    @staticmethod
    def detect_bias_flags(learning_summary: pd.DataFrame) -> pd.DataFrame:
        out = learning_summary.copy()

        def forecast_flag(x):
            if pd.isna(x):
                return "NO_DATA"
            if x > 5:
                return "UNDER_FORECASTING"
            if x < -5:
                return "OVER_FORECASTING"
            return "BALANCED"

        def budget_flag(x):
            if pd.isna(x):
                return "NO_DATA"
            if x > 5:
                return "UNDER_BUDGETING"
            if x < -5:
                return "OVER_BUDGETING"
            return "BALANCED"

        out["forecast_bias_flag"] = out["forecast_bias_pct"].apply(forecast_flag)
        out["budget_bias_flag"] = out["budget_bias_pct"].apply(budget_flag)
        return out