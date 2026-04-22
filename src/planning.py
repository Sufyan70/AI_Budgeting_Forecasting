import numpy as np
import pandas as pd


class RollingForecaster:
    def __init__(self, events_df=None, model_name="prophet"):
        self.events_df = events_df
        self.model_name = model_name

    def _model(self):
        from models import ProphetModel, SARIMAModel, LGBMModel, EnsembleModel, NaiveModel
        if self.model_name == "prophet":
            return ProphetModel(self.events_df)
        if self.model_name == "sarima":
            return SARIMAModel()
        if self.model_name == "lightgbm":
            return LGBMModel(events_df=self.events_df)
        if self.model_name == "naive":
            return NaiveModel()
        return EnsembleModel(self.events_df, use_lgbm=True)

    def run(self, df, horizon=3, min_train=12, freq="MS"):
        results = []
        total = max(1, len(df) - min_train - horizon + 1)
        print(f"  Rolling: {total} steps, horizon={horizon}")
        for i in range(total):
            train = df.iloc[: min_train + i].copy()
            test = df.iloc[min_train + i : min_train + i + horizon].copy()
            if len(test) == 0:
                break
            print(f"\r  Step {i + 1}/{total}", end="", flush=True)
            try:
                m = self._model()
                if self.model_name == "prophet":
                    m.fit(train)
                    pred = m.predict(horizon, freq)
                    pred = pred[pred["ds"] > train["ds"].max()].head(horizon).reset_index(drop=True)
                else:
                    m.fit(train, freq)
                    pred = m.predict(horizon, train["ds"].max(), freq)
                # for j in range(min(len(test), len(pred))):
                #     results.append({"ds": test.iloc[j]["ds"], "actual": test.iloc[j]["y"], "forecast": pred.iloc[j]["yhat"]})
                for j in range(min(len(test), len(pred))):
                    results.append({
                        "step_no": i + 1,
                        "train_end_date": train["ds"].max(),
                        "forecast_date": test.iloc[j]["ds"],
                        "ds": test.iloc[j]["ds"],
                        "actual": test.iloc[j]["y"],
                        "forecast": pred.iloc[j]["yhat"],
                        "horizon_step": j + 1,
    })
            except Exception:
                pass
        print()
        if not results:
            return pd.DataFrame()
        rdf = pd.DataFrame(results)
        rdf["error"] = rdf["actual"] - rdf["forecast"]
        rdf["abs_error"] = rdf["error"].abs()
        rdf["pct_error"] = rdf["abs_error"] / rdf["actual"].abs().clip(lower=1) * 100
        mae = rdf["abs_error"].mean()
        mape = rdf["pct_error"].mean()
        rmse = float(np.sqrt(np.mean(np.square(rdf["error"]))))
        bias_pct = float((rdf["error"].sum() / rdf["actual"].abs().clip(lower=1).sum()) * 100)
        print(f"  MAE: {mae:,.2f} | MAPE: {mape:.1f}% | RMSE: {rmse:,.2f} | Bias%: {bias_pct:.1f}%")
        return rdf


class ScenarioPlanner:
    @staticmethod
    def _apply_multiplier(df, multiplier, driver_name="scenario"):
        out = df.copy()
        for c in ["yhat", "yhat_lower", "yhat_upper"]:
            if c in out.columns:
                out[c] = out[c] * multiplier
        out["scenario_driver"] = driver_name
        out["scenario_multiplier"] = multiplier
        return out

    @classmethod
    def generate(
        cls,
        forecast,
        hist_std,
        growth_pct=0.0,
        ramzan_uplift_pct=0.0,
        event_uplift_pct=0.0,
        management_override_pct=0.0,
        churn_pct=0.0,
        new_branch_pct=0.0,
    ):
        scenarios = {}

        # Base
        base = forecast.copy()
        base["scenario_driver"] = "model_forecast"
        base["scenario_multiplier"] = 1.0
        scenarios["Base"] = base

        mean = forecast["yhat"].mean() if len(forecast) else 0
        factor = hist_std / mean if mean > 0 else 0.1

        # Conservative / downside
        cons_mult = max(0.5, 1.0 - factor + growth_pct / 100.0)
        scenarios["Conservative"] = cls._apply_multiplier(
            forecast, cons_mult, "downside_buffer"
        )

        # Aggressive / upside
        aggr_mult = 1.0 + factor + growth_pct / 100.0
        scenarios["Aggressive"] = cls._apply_multiplier(
            forecast, aggr_mult, "upside_buffer"
        )

        # Driver-based
        driver_multiplier = (
            1.0
            + growth_pct / 100.0
            + ramzan_uplift_pct / 100.0
            + event_uplift_pct / 100.0
            + management_override_pct / 100.0
            + new_branch_pct / 100.0
            - churn_pct / 100.0
        )
        scenarios["Driver_Based"] = cls._apply_multiplier(
            forecast, max(0.1, driver_multiplier), "growth_event_override"
        )

        if management_override_pct:
            scenarios["Management_Override"] = cls._apply_multiplier(
                forecast,
                1.0 + management_override_pct / 100.0,
                "management_override",
            )

        if ramzan_uplift_pct or event_uplift_pct:
            scenarios["Event_Push"] = cls._apply_multiplier(
                forecast,
                1.0 + ramzan_uplift_pct / 100.0 + event_uplift_pct / 100.0,
                "event_push",
            )

        return scenarios


class VarianceAnalyzer:
    @staticmethod
    def decompose_variance(actuals, fitted, budget_data=None):
        merged = actuals[["ds", "y"]].merge(
            fitted[["ds", "yhat"]].rename(columns={"yhat": "forecast"}), on="ds", how="inner"
        ).sort_values("ds")
        merged["total_variance"] = merged["y"] - merged["forecast"]
        merged["volume_variance"] = merged["total_variance"]
        merged["trend_variance"] = merged["forecast"].diff().fillna(0)
        merged["seasonality_variance"] = merged["y"].rolling(3, min_periods=1).mean() - merged["forecast"].rolling(3, min_periods=1).mean()
        merged["event_variance"] = merged["total_variance"] - merged["trend_variance"] - merged["seasonality_variance"]
        if budget_data is not None and len(budget_data) > 0:
            b = budget_data.copy()
            if "budget_amount" in b.columns and "budget" not in b.columns:
                b = b.rename(columns={"budget_amount": "budget"})
            merged = merged.merge(b[["ds", "budget"]], on="ds", how="left")
            merged["budget_variance"] = merged["y"] - merged["budget"]
        return merged

    @classmethod
    def run(cls, actuals, fitted, budget_data=None):
        merged = cls.decompose_variance(actuals, fitted, budget_data)
        merged["fc_var_pct"] = merged["total_variance"] / merged["forecast"].abs().clip(lower=1) * 100
        stats = {
            "fc_mae": float(merged["total_variance"].abs().mean()),
            "fc_mape": float(merged["fc_var_pct"].abs().mean()),
            "trend_var_mean": float(merged["trend_variance"].mean()),
            "seasonality_var_mean": float(merged["seasonality_variance"].mean()),
            "event_var_mean": float(merged["event_variance"].mean()),
        }
        if "budget_variance" in merged.columns:
            stats["bgt_mae"] = float(merged["budget_variance"].abs().mean())
        return merged, stats


class BudgetGenerator:

    @staticmethod
    def _seasonal_baseline(actuals_df: pd.DataFrame) -> pd.DataFrame:
        hist = actuals_df.copy()
        hist["ds"] = pd.to_datetime(hist["ds"])
        hist["month"] = hist["ds"].dt.month

        seasonal = (
            hist.groupby("month", dropna=False)["y"]
            .median()
            .reset_index()
            .rename(columns={"y": "seasonal_baseline"})
        )
        return seasonal

    @staticmethod
    def _recent_baseline(actuals_df: pd.DataFrame, window: int = 6) -> float:
        hist = actuals_df.copy().sort_values("ds")
        recent = hist["y"].tail(window)
        if len(recent) == 0:
            return 0.0
        return float(recent.median())

    @staticmethod
    def _trend_projection(actuals_df: pd.DataFrame, periods: int) -> pd.DataFrame:
        hist = actuals_df.copy().sort_values("ds").reset_index(drop=True)
        if len(hist) < 2:
            last_val = float(hist["y"].iloc[-1]) if len(hist) > 0 else 0.0
            return pd.DataFrame({"step": list(range(1, periods + 1)), "trend_projection": [last_val] * periods})

        x = np.arange(len(hist))
        y = hist["y"].astype(float).values

        slope, intercept = np.polyfit(x, y, 1)

        future_x = np.arange(len(hist), len(hist) + periods)
        future_y = intercept + slope * future_x

        future_y = np.where(future_y < 0, 0, future_y)

        return pd.DataFrame({
            "step": list(range(1, periods + 1)),
            "trend_projection": future_y
        })

    @staticmethod
    def generate(
        actuals_df: pd.DataFrame,
        forecast_df: pd.DataFrame | None = None,
        seasonal_weight: float = 0.5,
        rolling_weight: float = 0.3,
        trend_weight: float = 0.2,
        rolling_window: int = 6,
    ) -> pd.DataFrame:
        if actuals_df is None or len(actuals_df) == 0:
            raise ValueError("actuals_df is required for data-driven budget generation")

        hist = actuals_df.copy()
        hist["ds"] = pd.to_datetime(hist["ds"])
        hist = hist.sort_values("ds").reset_index(drop=True)

        if forecast_df is not None and len(forecast_df) > 0:
            fc = forecast_df.copy()
            fc["ds"] = pd.to_datetime(fc["ds"])
            fc = fc.sort_values("ds").reset_index(drop=True)
            periods = len(fc)
        else:
            raise ValueError("forecast_df is required to define future budget horizon")

        seasonal = BudgetGenerator._seasonal_baseline(hist)
        recent_baseline = BudgetGenerator._recent_baseline(hist, window=rolling_window)
        trend_df = BudgetGenerator._trend_projection(hist, periods=periods)

        out = fc.copy().reset_index(drop=True)
        out["step"] = np.arange(1, len(out) + 1)
        out["month"] = out["ds"].dt.month

        out = out.merge(seasonal, on="month", how="left")
        out = out.merge(trend_df, on="step", how="left")

        out["seasonal_baseline"] = out["seasonal_baseline"].fillna(recent_baseline)
        out["recent_baseline"] = recent_baseline
        out["trend_projection"] = out["trend_projection"].fillna(recent_baseline)

        total_weight = seasonal_weight + rolling_weight + trend_weight
        if total_weight == 0:
            raise ValueError("Budget weights cannot all be zero")

        seasonal_weight = seasonal_weight / total_weight
        rolling_weight = rolling_weight / total_weight
        trend_weight = trend_weight / total_weight

        out["budget"] = (
            seasonal_weight * out["seasonal_baseline"] +
            rolling_weight * out["recent_baseline"] +
            trend_weight * out["trend_projection"]
        )

        if "series" not in out.columns:
            out["series"] = "Total"

        return out[[
            "ds",
            "series",
            "budget",
            "seasonal_baseline",
            "recent_baseline",
            "trend_projection"
        ]]