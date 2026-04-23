from __future__ import annotations

import pandas as pd


class ForecastCalibrator:
    def __init__(self, window: int = 6, min_history: int = 3):
        self.window = max(1, int(window))
        self.min_history = max(1, int(min_history))
        self.profile = None

    def fit_calibrator(self, actuals: pd.DataFrame, fitted: pd.DataFrame, events_df: pd.DataFrame | None = None) -> dict:
        merged = actuals[["ds", "y"]].merge(
            fitted[["ds", "yhat"]].rename(columns={"yhat": "forecast_fit"}),
            on="ds", how="inner"
        ).sort_values("ds")
        merged = merged.dropna(subset=["y", "forecast_fit"])
        if len(merged) < self.min_history:
            self.profile = {
                "bias_add": 0.0,
                "bias_ratio": 1.0,
                "event_bias_ratio": 1.0,
                "event_bias_add": 0.0,
                "history_points": len(merged),
            }
            return self.profile
        tail = merged.tail(self.window).copy()
        tail["residual"] = tail["y"] - tail["forecast_fit"]

        bias_add = float(tail["residual"].mean())

        actual_sum = float(tail["y"].sum())
        fitted_sum = float(tail["forecast_fit"].sum())

        if fitted_sum <= 0:
            bias_ratio = 1.0
        else:
            bias_ratio = actual_sum / fitted_sum

        if pd.isna(bias_ratio) or bias_ratio <= 0:
            bias_ratio = 1.0

        bias_ratio = min(max(float(bias_ratio), 0.7), 1.5)

        event_bias_ratio = 1.0
        event_bias_add = 0.0
        if events_df is not None and len(events_df) > 0:
            ev = events_df[["ds", "holiday"]].copy()
            ev["ds"] = pd.to_datetime(ev["ds"])
            tagged = tail.merge(ev, on="ds", how="left")
            tagged["is_event"] = tagged["holiday"].notna()
            event_rows = tagged[tagged["is_event"]]
            if len(event_rows) >= self.min_history:
                event_bias_add = float(event_rows["residual"].mean())

                event_actual_sum = float(event_rows["y"].sum())
                event_fitted_sum = float(event_rows["forecast_fit"].sum())

                if event_fitted_sum > 0:
                    ev_ratio = event_actual_sum / event_fitted_sum
                    if pd.notna(ev_ratio) and ev_ratio > 0:
                        event_bias_ratio = float(min(max(ev_ratio, 0.7), 1.5))

        self.profile = {
            "bias_add": bias_add,
            "bias_ratio": bias_ratio,
            "event_bias_ratio": event_bias_ratio,
            "event_bias_add": event_bias_add,
            "history_points": len(merged),
        }
        return self.profile

    def apply_calibration(self, forecast_df: pd.DataFrame, events_df: pd.DataFrame | None = None) -> pd.DataFrame:
        if self.profile is None:
            out = forecast_df.copy()
            out["raw_forecast"] = out["yhat"]
            out["calibration_applied"] = 0
            return out
        out = forecast_df.copy()
        out["raw_forecast"] = out["yhat"]
        out["calibration_applied"] = 1
        multiplier = float(self.profile.get("bias_ratio", 1.0))
        bias_add = float(self.profile.get("bias_add", 0.0))

        out["yhat"] = out["yhat"] * multiplier + bias_add

        if "yhat_lower" in out.columns:
            out["yhat_lower"] = out["yhat_lower"] * multiplier + bias_add

        if "yhat_upper" in out.columns:
            out["yhat_upper"] = out["yhat_upper"] * multiplier + bias_add
        if events_df is not None and len(events_df) > 0:
            ev = events_df[["ds", "holiday"]].copy()
            ev["ds"] = pd.to_datetime(ev["ds"])
            out = out.merge(ev.assign(_is_event=1), on="ds", how="left")
            mask = out["_is_event"].fillna(0).astype(int) == 1
            if mask.any():
                ev_mult = float(self.profile.get("event_bias_ratio", 1.0))
                ev_add = float(self.profile.get("event_bias_add", 0.0))

                out.loc[mask, "yhat"] = out.loc[mask, "raw_forecast"] * ev_mult + ev_add

                if "yhat_lower" in out.columns:
                    out.loc[mask, "yhat_lower"] = out.loc[mask, "yhat_lower"] * ev_mult + ev_add

                if "yhat_upper" in out.columns:
                    out.loc[mask, "yhat_upper"] = out.loc[mask, "yhat_upper"] * ev_mult + ev_add
            out = out.drop(columns=[c for c in ["holiday", "_is_event"] if c in out.columns])
        return out

    @staticmethod
    def calibration_summary(profile: dict | None) -> dict:
        if not profile:
            return {}
        return {
            "history_points": profile.get("history_points"),
            "bias_add": round(float(profile.get("bias_add", 0.0)), 4),
            "bias_ratio": round(float(profile.get("bias_ratio", 1.0)), 4),
            "event_bias_ratio": round(float(profile.get("event_bias_ratio", 1.0)), 4),
            "final_multiplier": round(float(profile.get("bias_ratio", 1.0)), 4),
        }
