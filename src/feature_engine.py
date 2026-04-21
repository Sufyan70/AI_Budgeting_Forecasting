from __future__ import annotations

import numpy as np
import pandas as pd


class FeatureEngineer:
    def __init__(self, events_df=None):
        self.events_df = events_df.copy() if events_df is not None and len(events_df) > 0 else None
        if self.events_df is not None:
            self.events_df["ds"] = pd.to_datetime(self.events_df["ds"])

    def build_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        out["month"] = df["ds"].dt.month
        out["quarter"] = df["ds"].dt.quarter
        out["year"] = df["ds"].dt.year
        out["weekofyear"] = df["ds"].dt.isocalendar().week.astype(int)
        out["dayofweek"] = df["ds"].dt.dayofweek
        out["is_month_start"] = df["ds"].dt.is_month_start.astype(int)
        out["is_month_end"] = df["ds"].dt.is_month_end.astype(int)
        out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12)
        out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12)
        return out

    def build_lag_features(self, df: pd.DataFrame, lags=(1, 2, 3, 6, 12)) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        series = pd.Series(df["y"].values)
        for lag in lags:
            out[f"lag_{lag}"] = series.shift(lag)
        return out

    def build_roll_features(self, df: pd.DataFrame, windows=(3, 6, 12)) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        series = pd.Series(df["y"].values)
        for w in windows:
            out[f"roll_mean_{w}"] = series.rolling(w).mean()
            out[f"roll_std_{w}"] = series.rolling(w).std()
        return out

    def build_growth_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        series = pd.Series(df["y"].values)
        out["mom_growth"] = series.pct_change(1).replace([np.inf, -np.inf], np.nan)
        out["yoy_growth"] = series.pct_change(12).replace([np.inf, -np.inf], np.nan)
        return out

    def build_event_features(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        if self.events_df is None or len(self.events_df) == 0:
            out["event_count"] = 0
            out["ramzan_flag"] = 0
            out["eid_flag"] = 0
            return out
        merged = df[["ds"]].merge(self.events_df[["holiday", "ds"]], on="ds", how="left")
        grp = merged.groupby("ds")["holiday"].apply(list)
        out["event_count"] = df["ds"].map(lambda d: len([x for x in grp.get(d, []) if pd.notna(x)]))
        out["ramzan_flag"] = df["ds"].map(lambda d: int(any("ramzan" in str(x) for x in grp.get(d, []))))
        out["eid_flag"] = df["ds"].map(lambda d: int(any("eid" in str(x) for x in grp.get(d, []))))
        return out

    def assemble_features(self, df: pd.DataFrame) -> pd.DataFrame:
        parts = [
            self.build_time_features(df),
            self.build_lag_features(df),
            self.build_roll_features(df),
            self.build_growth_features(df),
            self.build_event_features(df),
        ]
        feat = pd.concat(parts, axis=1).fillna(0)
        return feat
